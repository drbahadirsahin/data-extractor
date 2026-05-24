from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from data_entry_store import DataEntryStore


class DynamicSqlError(RuntimeError):
    pass


@dataclass(frozen=True)
class DynamicQueryOption:
    value: str
    label: str


class DynamicSqlEvaluator:
    """
    Evaluates REDCap SQL field queries against the local redcap_data view.

    The supported target is intentionally narrow: SELECT-only REDCap SQL fields
    that read from redcap_data and use common MySQL expressions exported in the
    data dictionary. More complex REDCap/server-specific queries can be added
    incrementally when we see real examples that cannot be translated safely.
    """

    def __init__(self, store: DataEntryStore) -> None:
        self.store = store

    def evaluate(self, sql: str, *, record: str) -> list[DynamicQueryOption]:
        translated_sql, params = translate_dynamic_sql(sql, record=record)
        with self.store.connect() as db:
            register_mysql_compat_functions(db)
            install_readonly_authorizer(db)
            try:
                rows = db.execute(translated_sql, params).fetchall()
            except sqlite3.Error as exc:
                raise DynamicSqlError(f"Dynamic SQL could not be evaluated locally: {exc}") from exc
            finally:
                db.set_authorizer(None)
        return options_from_rows(rows)


def translate_dynamic_sql(sql: str, *, record: str) -> tuple[str, list[Any]]:
    cleaned = normalize_dynamic_sql(sql)
    validate_dynamic_sql(cleaned)
    translated = rewrite_group_concat_separator(cleaned)
    placeholder_count = translated.count("[record-name]")
    if placeholder_count == 0:
        return translated, []
    translated = translated.replace("[record-name]", "?")
    return translated, [str(record)] * placeholder_count


def normalize_dynamic_sql(sql: str) -> str:
    cleaned = str(sql or "").strip()
    if not cleaned:
        raise DynamicSqlError("Dynamic SQL is empty.")
    return cleaned[:-1].strip() if cleaned.endswith(";") else cleaned


def validate_dynamic_sql(sql: str) -> None:
    stripped = sql.strip()
    lowered = stripped.lower()
    if not lowered.startswith("select "):
        raise DynamicSqlError("Only SELECT dynamic SQL queries can be evaluated locally.")
    if ";" in stripped:
        raise DynamicSqlError("Multiple SQL statements are not allowed.")
    if not re.search(r"\bfrom\s+redcap_data\b", lowered):
        raise DynamicSqlError("Only dynamic SQL queries reading from redcap_data are supported locally.")
    disallowed = re.search(
        r"\b(insert|update|delete|drop|alter|create|replace|truncate|attach|detach|pragma|vacuum)\b",
        lowered,
    )
    if disallowed:
        raise DynamicSqlError(f"Unsupported SQL keyword: {disallowed.group(1)}")


def rewrite_group_concat_separator(sql: str) -> str:
    result: list[str] = []
    cursor = 0
    while True:
        match = re.search(r"group_concat\s*\(", sql[cursor:], flags=re.IGNORECASE)
        if match is None:
            result.append(sql[cursor:])
            break
        start = cursor + match.start()
        open_index = sql.find("(", start)
        close_index = find_matching_paren(sql, open_index)
        if close_index < 0:
            raise DynamicSqlError("Unbalanced GROUP_CONCAT expression.")

        result.append(sql[cursor:start])
        inner = sql[open_index + 1 : close_index]
        split = split_top_level_separator(inner)
        if split is None:
            result.append(sql[start : close_index + 1])
        else:
            expression, separator = split
            result.append(f"GROUP_CONCAT({expression.strip()}, {separator.strip()})")
        cursor = close_index + 1
    return "".join(result)


def split_top_level_separator(inner: str) -> tuple[str, str] | None:
    depth = 0
    quote: str | None = None
    index = 0
    while index < len(inner):
        char = inner[index]
        if quote:
            if char == quote:
                if index + 1 < len(inner) and inner[index + 1] == quote:
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if char == "(":
            depth += 1
            index += 1
            continue
        if char == ")":
            depth = max(0, depth - 1)
            index += 1
            continue
        if depth == 0 and inner[index : index + 9].lower() == "separator":
            before_ok = index == 0 or inner[index - 1].isspace()
            after_index = index + 9
            after_ok = after_index >= len(inner) or inner[after_index].isspace()
            if before_ok and after_ok:
                return inner[:index], inner[after_index:]
        index += 1
    return None


def find_matching_paren(sql: str, open_index: int) -> int:
    depth = 0
    quote: str | None = None
    index = open_index
    while index < len(sql):
        char = sql[index]
        if quote:
            if char == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1


def register_mysql_compat_functions(db: sqlite3.Connection) -> None:
    db.create_function("CONCAT", -1, mysql_concat)
    db.create_function("IF", 3, mysql_if)


def install_readonly_authorizer(db: sqlite3.Connection) -> None:
    allowed = {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
    }

    def authorizer(action: int, p1: str | None, p2: str | None, db_name: str | None, source: str | None) -> int:
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY

    db.set_authorizer(authorizer)


def mysql_concat(*args: Any) -> str | None:
    if any(arg is None for arg in args):
        return None
    return "".join(str(arg) for arg in args)


def mysql_if(condition: Any, truthy: Any, falsy: Any) -> Any:
    return truthy if bool(condition) else falsy


def options_from_rows(rows: list[sqlite3.Row]) -> list[DynamicQueryOption]:
    options: list[DynamicQueryOption] = []
    for row in rows:
        keys = row.keys()
        if "value" in keys:
            value = row["value"]
            label = row["label"] if "label" in keys else value
        elif len(keys) >= 2:
            value = row[0]
            label = row[1]
        elif len(keys) == 1:
            value = row[0]
            label = row[0]
        else:
            continue
        if value in {None, ""}:
            continue
        options.append(DynamicQueryOption(value=str(value), label=str(label if label not in {None, ""} else value)))
    return options
