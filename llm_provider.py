from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from http_client import urlopen

DEFAULT_HTTP_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36 LLMExtractor/1.0"
    ),
}
API_KEY_PROVIDER_NAMES = {"openai", "openai_compatible", "openrouter"}
GATEWAY_PROVIDER_NAMES = {"llm_gateway", "managed_gateway"}
DEFAULT_API_KEY_SECRET_NAME = "llm_api_key"
DEFAULT_GATEWAY_CLIENT_TOKEN_SECRET_NAME = "llm_gateway_client_token"
logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    content: str | None
    thinking: str | None = None
    raw: Any = None
    request_id: str | None = None
    model: str | None = None
    provider: str | None = None
    finish_reason: str | None = None
    native_finish_reason: str | None = None


class ProviderHTTPError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class ProviderResponseError(RuntimeError):
    """A safe, content-free error reported inside a provider response."""

    def __init__(
        self,
        message: str,
        *,
        request_id: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        finish_reason: str | None = None,
        native_finish_reason: str | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.request_id = request_id
        self.model = model
        self.provider = provider
        self.finish_reason = finish_reason
        self.native_finish_reason = native_finish_reason
        self.error_code = error_code


class LLMProvider:
    def generate(
        self,
        messages: list[dict[str, Any]],
        schema: dict[str, Any],
        settings: dict[str, Any],
    ) -> LLMResponse:
        raise NotImplementedError


class OllamaProvider(LLMProvider):
    def generate(
        self,
        messages: list[dict[str, Any]],
        schema: dict[str, Any],
        settings: dict[str, Any],
    ) -> LLMResponse:
        base_url = normalize_base_url(settings.get("base_url", "http://127.0.0.1:11434"))
        stream = bool(settings.get("stream", True))
        payload = {
            "model": settings["model"],
            "messages": messages,
            "format": schema,
            "think": bool(settings.get("think", False)),
            "stream": stream,
            "options": build_ollama_options(settings),
        }
        timeout_seconds = int(settings.get("timeout_seconds", 600))
        if stream:
            response = post_json_stream(
                f"{base_url}/api/chat",
                payload=dict(payload),
                headers=coerce_string_dict(settings.get("headers", {})),
                timeout_seconds=timeout_seconds,
            )
        else:
            response = post_json(
                f"{base_url}/api/chat",
                payload=dict(payload),
                headers=coerce_string_dict(settings.get("headers", {})),
                timeout_seconds=timeout_seconds,
            )
        message = response.get("message") or {}
        return LLMResponse(
            content=message.get("content"),
            thinking=message.get("thinking"),
            raw=response,
        )


class OpenAICompatibleProvider(LLMProvider):
    def generate(
        self,
        messages: list[dict[str, Any]],
        schema: dict[str, Any],
        settings: dict[str, Any],
    ) -> LLMResponse:
        base_url = normalize_base_url(settings["base_url"])
        headers = {
            "Content-Type": "application/json",
            **coerce_string_dict(settings.get("headers", {})),
        }
        auth_headers = build_auth_headers(settings)
        headers.update(auth_headers)
        timeout_seconds = int(settings.get("timeout_seconds", 120))
        payload = {
            "model": settings["model"],
            "messages": messages,
            "temperature": settings.get("temperature", 0),
            "max_tokens": settings.get("max_tokens", 8192),
        }
        reasoning = build_openai_reasoning(settings)
        if reasoning is not None:
            payload["reasoning"] = reasoning
        extra_body = settings.get("extra_body", {})
        if isinstance(extra_body, dict):
            payload.update(extra_body)
        plugins = settings.get("plugins", [])
        if isinstance(plugins, list) and plugins:
            payload["plugins"] = plugins

        use_json_schema = bool(settings.get("use_json_schema", True))
        if use_json_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "extraction_response",
                    "strict": True,
                    "schema": schema,
                },
            }

        try:
            response = post_json(
                f"{base_url}/chat/completions",
                payload=dict(payload),
                headers=headers,
                timeout_seconds=timeout_seconds,
            )
        except ProviderHTTPError as exc:
            if use_json_schema and should_retry_without_json_schema(exc):
                payload.pop("response_format", None)
                payload["messages"] = add_json_only_fallback_message(messages, schema)
                response = post_json(
                    f"{base_url}/chat/completions",
                    payload=dict(payload),
                    headers=headers,
                    timeout_seconds=timeout_seconds,
                )
            else:
                raise

        response_metadata = extract_openai_response_metadata(response)
        raw_choices = response.get("choices")
        raw_choice = raw_choices[0] if isinstance(raw_choices, list) and raw_choices else {}
        choice = raw_choice if isinstance(raw_choice, dict) else {}
        response_metadata["finish_reason"] = optional_metadata_text(choice.get("finish_reason"))
        response_metadata["native_finish_reason"] = optional_metadata_text(choice.get("native_finish_reason"))
        top_level_error = response.get("error")
        if top_level_error is not None:
            raise_openai_response_error(
                "LLM provider returned an error response.",
                response_metadata,
                error_code=extract_provider_error_code(top_level_error),
                outcome="top_level_error",
            )

        choice_error = choice.get("error")
        if choice_error is not None:
            raise_openai_response_error(
                "LLM provider returned a completion error.",
                response_metadata,
                error_code=extract_provider_error_code(choice_error),
                outcome="choice_error",
            )

        raw_message = choice.get("message")
        message = raw_message if isinstance(raw_message, dict) else {}
        if message.get("refusal"):
            raise_openai_response_error(
                "LLM provider refused the request.",
                response_metadata,
                outcome="refusal",
            )

        normalized_finish_reason = str(response_metadata.get("finish_reason") or "").strip().lower()
        if normalized_finish_reason in {"error", "content_filter"}:
            error_message = (
                "LLM provider blocked the response through its content filter."
                if normalized_finish_reason == "content_filter"
                else "LLM provider could not complete the response."
            )
            raise_openai_response_error(
                error_message,
                response_metadata,
                outcome=normalized_finish_reason,
            )

        log_openai_response_metadata(
            response_metadata,
            outcome="truncated" if normalized_finish_reason == "length" else "completed",
            warning=normalized_finish_reason == "length",
        )
        return LLMResponse(
            content=extract_openai_content(message.get("content")),
            thinking=extract_openai_content(message.get("reasoning") or message.get("thinking")),
            raw=response,
            **response_metadata,
        )


def create_provider(settings: dict[str, Any]) -> LLMProvider:
    provider_name = str(settings.get("provider", "ollama")).strip().lower()
    if provider_name == "ollama":
        return OllamaProvider()
    if provider_name in API_KEY_PROVIDER_NAMES or provider_name in GATEWAY_PROVIDER_NAMES:
        return OpenAICompatibleProvider()
    raise ValueError(f"Unsupported LLM provider: {provider_name}")


def merge_llm_settings(app_settings: dict[str, Any], project_settings: dict[str, Any]) -> dict[str, Any]:
    merged = dict(app_settings or {})
    merged.update(project_settings or {})
    return merged


def resolve_api_key(settings: dict[str, Any]) -> str:
    direct_value = settings.get("api_key")
    if direct_value:
        return str(direct_value)
    env_var = settings.get("api_key_env")
    if env_var:
        env_value = os.getenv(str(env_var))
        if env_value:
            return env_value
        raise ValueError(f"Missing API key in environment variable: {env_var}")
    secret_name = str(settings.get("api_key_secret_name") or DEFAULT_API_KEY_SECRET_NAME).strip()
    if secret_name:
        secret_value = resolve_api_key_from_secret_store(secret_name)
        if secret_value:
            return secret_value
    raise ValueError(
        "Missing API key. Provide llm.api_key, llm.api_key_env, "
        f"or save a key as {secret_name or DEFAULT_API_KEY_SECRET_NAME}."
    )


def build_auth_headers(settings: dict[str, Any]) -> dict[str, str]:
    provider_name = str(settings.get("provider", "")).strip().lower()
    if provider_name in GATEWAY_PROVIDER_NAMES or str(settings.get("auth", "")).strip().lower() == "none":
        gateway_token = resolve_gateway_client_token(settings)
        if gateway_token:
            return {"Authorization": f"Bearer {gateway_token}"}
        return {}
    return {"Authorization": f"Bearer {resolve_api_key(settings)}"}


def resolve_gateway_client_token(settings: dict[str, Any]) -> str | None:
    direct_value = settings.get("gateway_client_token")
    if direct_value:
        return str(direct_value)
    env_var = settings.get("gateway_client_token_env")
    if env_var:
        env_value = os.getenv(str(env_var))
        if env_value:
            return env_value
    secret_name = str(
        settings.get("gateway_client_token_secret_name") or DEFAULT_GATEWAY_CLIENT_TOKEN_SECRET_NAME
    ).strip()
    if secret_name:
        secret_value = resolve_api_key_from_secret_store(secret_name)
        if secret_value:
            return secret_value
    return None


def can_resolve_api_key(settings: dict[str, Any]) -> bool:
    provider_name = str(settings.get("provider", "")).strip().lower()
    if provider_name in GATEWAY_PROVIDER_NAMES or str(settings.get("auth", "")).strip().lower() == "none":
        return True
    try:
        resolve_api_key(settings)
    except ValueError:
        return False
    return True


def resolve_api_key_from_secret_store(secret_name: str) -> str | None:
    try:
        from secrets_store import SecretsStore
    except Exception:
        return None
    try:
        value = SecretsStore().get(secret_name)
    except Exception:
        return None
    return value or None


def normalize_base_url(base_url: str) -> str:
    return str(base_url).rstrip("/")


def coerce_string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def build_ollama_options(settings: dict[str, Any]) -> dict[str, Any]:
    options = {
        "temperature": settings.get("temperature", 0),
        "num_predict": settings.get("max_tokens", 8192),
    }
    extra_options = settings.get("options", {})
    if isinstance(extra_options, dict):
        options.update(extra_options)
    return options


def build_openai_reasoning(settings: dict[str, Any]) -> dict[str, Any] | None:
    configured_reasoning = settings.get("reasoning")
    if isinstance(configured_reasoning, dict):
        return configured_reasoning
    if "think" in settings:
        if settings.get("think"):
            return {"enabled": True}
        return {"effort": "none", "exclude": True}
    return None


def extract_openai_content(content: Any) -> str | None:
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
        return "".join(parts) or None
    return str(content)


def optional_metadata_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def extract_openai_response_metadata(response: dict[str, Any]) -> dict[str, str | None]:
    return {
        "request_id": optional_metadata_text(response.get("id")),
        "model": optional_metadata_text(response.get("model")),
        "provider": optional_metadata_text(response.get("provider")),
        "finish_reason": None,
        "native_finish_reason": None,
    }


def extract_provider_error_code(provider_error: Any) -> str | None:
    if not isinstance(provider_error, dict):
        return None
    return optional_metadata_text(provider_error.get("code"))


def safe_log_metadata_value(value: Any, *, limit: int = 200) -> str:
    if value is None:
        return "-"
    text = "".join(character if character.isprintable() else " " for character in str(value))
    text = " ".join(text.split())
    return text[:limit] or "-"


def log_openai_response_metadata(
    metadata: dict[str, str | None],
    *,
    outcome: str,
    warning: bool = False,
    error_code: str | None = None,
) -> None:
    log = logger.warning if warning else logger.info
    log(
        "LLM response metadata: outcome=%s request_id=%s model=%s provider=%s "
        "finish_reason=%s native_finish_reason=%s error_code=%s",
        safe_log_metadata_value(outcome),
        safe_log_metadata_value(metadata.get("request_id")),
        safe_log_metadata_value(metadata.get("model")),
        safe_log_metadata_value(metadata.get("provider")),
        safe_log_metadata_value(metadata.get("finish_reason")),
        safe_log_metadata_value(metadata.get("native_finish_reason")),
        safe_log_metadata_value(error_code),
    )


def raise_openai_response_error(
    message: str,
    metadata: dict[str, str | None],
    *,
    outcome: str,
    error_code: str | None = None,
) -> None:
    log_openai_response_metadata(
        metadata,
        outcome=outcome,
        warning=True,
        error_code=error_code,
    )
    raise ProviderResponseError(
        message,
        request_id=metadata.get("request_id"),
        model=metadata.get("model"),
        provider=metadata.get("provider"),
        finish_reason=metadata.get("finish_reason"),
        native_finish_reason=metadata.get("native_finish_reason"),
        error_code=error_code,
    )


def should_retry_without_json_schema(exc: ProviderHTTPError) -> bool:
    body = (exc.body or "").lower()
    return any(
        token in body
        for token in [
            "response_format",
            "json_schema",
            "schema",
            "unsupported",
            "invalid request",
        ]
    )


def add_json_only_fallback_message(messages: list[dict[str, Any]], schema: dict[str, Any]) -> list[dict[str, Any]]:
    schema_snippet = json.dumps(schema, ensure_ascii=False)
    fallback_instruction = {
        "role": "system",
        "content": (
            "Return valid JSON only. The response must match this JSON schema exactly: "
            f"{schema_snippet}"
        ),
    }
    return [fallback_instruction, *messages]


def post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: int,
) -> dict[str, Any]:
    request_headers = {
        **DEFAULT_HTTP_HEADERS,
        "Content-Type": "application/json",
        **headers,
    }
    body = json.dumps(payload).encode("utf-8")
    http_request = request.Request(url=url, data=body, headers=request_headers, method="POST")
    try:
        with urlopen(http_request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        if exc.code == 403 and "error code: 1010" in error_body.lower():
            raise ProviderHTTPError(
                "LLM provider request was blocked by Cloudflare (error 1010). "
                "This usually means the proxy rejected the client signature or User-Agent. "
                "Try a browser-like User-Agent via llm.headers or relax the proxy firewall settings.",
                status_code=exc.code,
                body=error_body,
            ) from exc
        raise ProviderHTTPError(
            f"LLM provider request failed with HTTP {exc.code}: {error_body[:500]}",
            status_code=exc.code,
            body=error_body,
        ) from exc
    except error.URLError as exc:
        raise ProviderHTTPError(f"LLM provider request failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ProviderHTTPError(f"LLM provider request timed out after {timeout_seconds} seconds.") from exc

    try:
        return json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM provider returned invalid JSON response: {response_body[:500]}") from exc


def post_json_stream(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: int,
) -> dict[str, Any]:
    request_headers = {
        **DEFAULT_HTTP_HEADERS,
        "Content-Type": "application/json",
        **headers,
    }
    body = json.dumps(payload).encode("utf-8")
    http_request = request.Request(url=url, data=body, headers=request_headers, method="POST")
    chunks: list[dict[str, Any]] = []
    content_parts: list[str] = []
    thinking_parts: list[str] = []
    final_chunk: dict[str, Any] = {}
    try:
        with urlopen(http_request, timeout=timeout_seconds) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"LLM provider returned invalid JSON stream chunk: {line[:500]}") from exc
                if chunk.get("error"):
                    raise ProviderHTTPError(f"LLM provider returned an error: {chunk.get('error')}")
                chunks.append(chunk)
                message = chunk.get("message") or {}
                content = message.get("content")
                thinking = message.get("thinking")
                if content:
                    content_parts.append(str(content))
                if thinking:
                    thinking_parts.append(str(thinking))
                if chunk.get("done"):
                    final_chunk = chunk
    except error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise ProviderHTTPError(
            f"LLM provider request failed with HTTP {exc.code}: {error_body[:500]}",
            status_code=exc.code,
            body=error_body,
        ) from exc
    except error.URLError as exc:
        raise ProviderHTTPError(f"LLM provider request failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ProviderHTTPError(
            f"LLM provider stream timed out after {timeout_seconds} seconds without receiving the next chunk."
        ) from exc

    return {
        **final_chunk,
        "message": {
            "content": "".join(content_parts),
            "thinking": "".join(thinking_parts) or None,
        },
        "chunks": chunks,
    }
