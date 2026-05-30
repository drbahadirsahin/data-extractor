from __future__ import annotations

import ast
import math
import operator
import re
from typing import Any


FIELD_REF_PATTERN = re.compile(r"\[([A-Za-z0-9_]+)(?:\(([^)\]]+)\))?\]")


class RedcapCalcError(ValueError):
    pass


def redcap_calc_field_names(expression: str | None) -> set[str]:
    names: set[str] = set()
    for match in FIELD_REF_PATTERN.finditer(str(expression or "")):
        field_name, checkbox_code = match.groups()
        names.add(f"{field_name}___{checkbox_code}" if checkbox_code else field_name)
    return names


def evaluate_redcap_calc(expression: str | None, values: dict[str, Any]) -> str:
    text = str(expression or "").strip()
    if not text:
        return ""
    referenced = redcap_calc_field_names(text)
    if any(not value_is_present(values.get(field_name)) for field_name in referenced):
        return ""
    try:
        python_expression = redcap_expression_to_python(text)
        tree = ast.parse(python_expression, mode="eval")
        result = SafeRedcapCalcEvaluator(values).evaluate(tree)
    except Exception:
        return ""
    return format_calc_result(result)


def redcap_expression_to_python(expression: str) -> str:
    converted = FIELD_REF_PATTERN.sub(field_reference_replacement, str(expression))
    converted = re.sub(r"\bif\s*\(", "if_func(", converted, flags=re.IGNORECASE)
    converted = converted.replace("^", "**")
    converted = converted.replace("<>", "!=")
    converted = re.sub(r"(?<![<>=!])=(?!=)", "==", converted)
    return converted


def field_reference_replacement(match: re.Match[str]) -> str:
    field_name, checkbox_code = match.groups()
    key = f"{field_name}___{checkbox_code}" if checkbox_code else field_name
    return f"field({key!r})"


class SafeRedcapCalcEvaluator:
    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values

    def evaluate(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return self.evaluate(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BinOp):
            left = self.evaluate(node.left)
            right = self.evaluate(node.right)
            return evaluate_binary_operation(node.op, left, right)
        if isinstance(node, ast.UnaryOp):
            value = self.evaluate(node.operand)
            return evaluate_unary_operation(node.op, value)
        if isinstance(node, ast.Compare):
            return self.evaluate_compare(node)
        if isinstance(node, ast.BoolOp):
            values = [bool(self.evaluate(value)) for value in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            if isinstance(node.op, ast.Or):
                return any(values)
        if isinstance(node, ast.Call):
            return self.evaluate_call(node)
        raise RedcapCalcError(f"Unsupported REDCap calc syntax: {ast.dump(node)}")

    def evaluate_compare(self, node: ast.Compare) -> bool:
        left = self.evaluate(node.left)
        for operator_node, comparator in zip(node.ops, node.comparators, strict=False):
            right = self.evaluate(comparator)
            if not compare_values(left, operator_node, right):
                return False
            left = right
        return True

    def evaluate_call(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Name):
            raise RedcapCalcError("Only simple REDCap calc functions are supported")
        name = node.func.id.lower()
        if name == "field":
            if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant):
                raise RedcapCalcError("Invalid field reference")
            return value_for_field(self.values, str(node.args[0].value))
        args = [self.evaluate(arg) for arg in node.args]
        if name == "if_func":
            if len(args) != 3:
                raise RedcapCalcError("if() expects three arguments")
            return args[1] if bool(args[0]) else args[2]
        if name == "round":
            if len(args) == 1:
                return round(float(args[0]))
            if len(args) == 2:
                return round(float(args[0]), int(float(args[1])))
            raise RedcapCalcError("round() expects one or two arguments")
        if name == "sum":
            return sum(float(arg) for arg in args)
        if name in {"min", "max"}:
            return min(*args) if name == "min" else max(*args)
        if name == "abs":
            return abs(float(args[0]))
        if name == "sqrt":
            return math.sqrt(float(args[0]))
        if name == "floor":
            return math.floor(float(args[0]))
        if name == "ceil":
            return math.ceil(float(args[0]))
        raise RedcapCalcError(f"Unsupported REDCap calc function: {name}")


def evaluate_binary_operation(operator_node: ast.operator, left: Any, right: Any) -> Any:
    operations: dict[type[ast.operator], Any] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.Mod: operator.mod,
    }
    operation = operations.get(type(operator_node))
    if operation is None:
        raise RedcapCalcError("Unsupported arithmetic operator")
    return operation(float(left), float(right))


def evaluate_unary_operation(operator_node: ast.unaryop, value: Any) -> Any:
    if isinstance(operator_node, ast.USub):
        return -float(value)
    if isinstance(operator_node, ast.UAdd):
        return float(value)
    raise RedcapCalcError("Unsupported unary operator")


def compare_values(left: Any, operator_node: ast.cmpop, right: Any) -> bool:
    left_number = parse_number(left)
    right_number = parse_number(right)
    left_value = left_number if left_number is not None and right_number is not None else str(left)
    right_value = right_number if left_number is not None and right_number is not None else str(right)
    if isinstance(operator_node, ast.Eq):
        return left_value == right_value
    if isinstance(operator_node, ast.NotEq):
        return left_value != right_value
    if isinstance(operator_node, ast.Gt):
        return left_value > right_value
    if isinstance(operator_node, ast.GtE):
        return left_value >= right_value
    if isinstance(operator_node, ast.Lt):
        return left_value < right_value
    if isinstance(operator_node, ast.LtE):
        return left_value <= right_value
    raise RedcapCalcError("Unsupported comparison operator")


def value_for_field(values: dict[str, Any], field_name: str) -> Any:
    value = values.get(field_name, "")
    number = parse_number(value)
    return number if number is not None else str(value)


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def value_is_present(value: Any) -> bool:
    if isinstance(value, list):
        return any(str(item or "").strip() for item in value)
    return str(value or "").strip() != ""


def format_calc_result(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    number = parse_number(value)
    if number is None:
        return str(value or "")
    if math.isfinite(number) and number.is_integer():
        return str(int(number))
    return f"{number:.10g}"
