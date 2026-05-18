from __future__ import annotations

from dataclasses import dataclass

from runtime_context import RuntimeContext
from gui.i18n import tr


@dataclass
class ProviderOption:
    key: str
    label_key: str
    description_key: str


PROVIDER_OPTIONS = [
    ProviderOption(
        key="local_ollama",
        label_key="provider_local_ollama",
        description_key="provider_desc_local_ollama",
    ),
    ProviderOption(
        key="remote_ollama",
        label_key="provider_remote_ollama",
        description_key="provider_desc_remote_ollama",
    ),
    ProviderOption(
        key="openai_compatible",
        label_key="provider_openai_compatible",
        description_key="provider_desc_openai_compatible",
    ),
]


def get_provider_options(language: str) -> list[ProviderOption]:
    return [
        ProviderOption(
            key=option.key,
            label_key=tr(option.label_key, language),
            description_key=tr(option.description_key, language),
        )
        for option in PROVIDER_OPTIONS
    ]


def provider_label_for_key(key: str | None, language: str = "tr") -> str:
    for option in PROVIDER_OPTIONS:
        if option.key == key:
            return tr(option.label_key, language)
    return tr("provider_unknown", language)


def build_system_summary(context: RuntimeContext) -> list[str]:
    language = context.settings.ui.language
    profile = context.system_profile
    gpu_summary = ", ".join(
        f"{gpu.name} ({gpu.memory_gb:.1f} GB)" if gpu.memory_gb is not None else gpu.name
        for gpu in profile.gpus
    ) or tr("no_nvidia_gpu", language)
    memory_summary = (
        tr("summary_ram", language, value=f"{profile.total_memory_gb:.1f} GB")
        if profile.total_memory_gb is not None
        else tr("summary_ram", language, value="?")
    )
    return [
        tr("summary_os", language, value=f"{profile.os_name} {profile.machine}"),
        tr("summary_cpu", language, value=profile.cpu_count),
        memory_summary,
        tr("summary_gpu", language, value=gpu_summary),
    ]


def build_recommendation_text(context: RuntimeContext) -> str:
    language = context.settings.ui.language
    recommendation = context.inference_recommendation
    reason_text = " ".join(recommendation.reasons)
    return tr(
        "recommendation",
        language,
        provider=provider_label_for_key(recommendation.mode, language),
        confidence=recommendation.confidence,
        reasons=reason_text,
    )


def get_initial_page_index(context: RuntimeContext) -> int:
    has_redcap_credentials = bool(
        context.settings.redcap.api_url
        and (
            context.settings.redcap.saved_project_tokens
            or context.secrets_store.has(context.settings.redcap.api_token_secret_name)
        )
    )
    if context.settings.first_run_completed and has_redcap_credentials:
        return 1
    return 0
