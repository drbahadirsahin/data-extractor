from __future__ import annotations

from redcap_client import RedcapAPIError, RedcapClient, RedcapProject
from runtime_context import RuntimeContext
from gui.i18n import tr
from gui.view_models import build_recommendation_text, build_system_summary, get_provider_options
from settings_store import RedcapProjectToken


class OnboardingPage:
    def __init__(self, runtime: RuntimeContext) -> None:
        from PySide6.QtWidgets import (
            QComboBox,
            QFormLayout,
            QFrame,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QListWidget,
            QListWidgetItem,
            QPushButton,
            QVBoxLayout,
            QWidget,
        )

        self.runtime = runtime
        self.language = runtime.settings.ui.language
        self.widget = QWidget()
        self.validated_project: RedcapProject | None = None

        root = QVBoxLayout(self.widget)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(24, 24, 24, 24)
        hero_layout.setSpacing(10)

        hero_title = QLabel(tr("onboarding_title", self.language))
        hero_title.setObjectName("TitleLabel")
        hero_layout.addWidget(hero_title)

        hero_summary = QLabel(build_recommendation_text(runtime))
        hero_summary.setWordWrap(True)
        hero_summary.setObjectName("MutedLabel")
        hero_layout.addWidget(hero_summary)

        self.system_list = QListWidget()
        for line in build_system_summary(runtime):
            QListWidgetItem(line, self.system_list)
        hero_layout.addWidget(self.system_list)
        root.addWidget(hero)

        panels_row = QHBoxLayout()
        panels_row.setSpacing(18)

        provider_card = QFrame()
        provider_card.setObjectName("PanelCard")
        provider_layout = QVBoxLayout(provider_card)
        provider_layout.setContentsMargins(20, 20, 20, 20)
        provider_layout.setSpacing(12)
        provider_title = QLabel(tr("onboarding_inference", self.language))
        provider_title.setObjectName("SectionLabel")
        provider_layout.addWidget(provider_title)

        form = QFormLayout()
        form.setSpacing(10)
        self.language_combo = QComboBox()
        self.language_combo.addItem(tr("language_tr", self.language), "tr")
        self.language_combo.addItem(tr("language_en", self.language), "en")
        self._set_combo_value(self.language_combo, runtime.settings.ui.language)

        self.provider_combo = QComboBox()
        for option in get_provider_options(self.language):
            self.provider_combo.addItem(option.label_key, option.key)
        current_provider = runtime.settings.inference.selected_provider or runtime.inference_recommendation.mode
        self._set_combo_value(self.provider_combo, current_provider)
        self.provider_combo.currentIndexChanged.connect(self.update_provider_fields_visibility)

        self.local_url_input = QLineEdit(runtime.settings.inference.local_ollama_base_url)
        self.remote_url_input = QLineEdit(runtime.settings.inference.remote_ollama_base_url or "")
        self.api_url_input = QLineEdit(runtime.settings.inference.openai_compatible_base_url or "")
        self.api_model_input = QLineEdit(runtime.settings.inference.openai_compatible_model or "")
        self.api_key_input = QLineEdit("")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        if self.runtime.secrets_store.has(runtime.settings.inference.api_key_secret_name):
            self.api_key_input.setPlaceholderText(tr("api_key_saved_placeholder", self.language))

        self.language_label = QLabel(tr("onboarding_language", self.language))
        self.provider_label = QLabel(tr("provider_label", self.language))
        self.local_url_label = QLabel(tr("local_ollama_url", self.language))
        self.remote_url_label = QLabel(tr("remote_ollama_url", self.language))
        self.api_url_label = QLabel(tr("api_base_url", self.language))
        self.api_model_label = QLabel(tr("api_model", self.language))
        self.api_key_label = QLabel(tr("api_key", self.language))

        form.addRow(self.language_label, self.language_combo)
        form.addRow(self.provider_label, self.provider_combo)
        form.addRow(self.local_url_label, self.local_url_input)
        form.addRow(self.remote_url_label, self.remote_url_input)
        form.addRow(self.api_url_label, self.api_url_input)
        form.addRow(self.api_model_label, self.api_model_input)
        form.addRow(self.api_key_label, self.api_key_input)
        provider_layout.addLayout(form)

        self.save_provider_button = QPushButton(tr("save_inference", self.language))
        self.save_provider_button.clicked.connect(self.save_inference_settings)
        provider_layout.addWidget(self.save_provider_button)
        self.provider_status = QLabel("")
        self.provider_status.setObjectName("MutedLabel")
        provider_layout.addWidget(self.provider_status)
        panels_row.addWidget(provider_card, 1)

        redcap_card = QFrame()
        redcap_card.setObjectName("PanelCard")
        redcap_layout = QVBoxLayout(redcap_card)
        redcap_layout.setContentsMargins(20, 20, 20, 20)
        redcap_layout.setSpacing(12)
        redcap_title = QLabel(tr("onboarding_redcap", self.language))
        redcap_title.setObjectName("SectionLabel")
        redcap_layout.addWidget(redcap_title)
        redcap_layout.addWidget(QLabel(tr("redcap_token_hint", self.language)))

        redcap_form = QFormLayout()
        redcap_form.setSpacing(10)
        configured_redcap_url = (
            self._normalize_optional(runtime.settings.redcap.api_url)
            or self._normalize_optional(runtime.app_config.get("redcap", {}).get("api_url", ""))
        )
        self.redcap_url_input = QLineEdit(configured_redcap_url or "")
        allow_api_url_edit = bool(runtime.app_config.get("redcap", {}).get("allow_api_url_edit", False))
        if not configured_redcap_url:
            allow_api_url_edit = True
        self.redcap_url_input.setReadOnly(not allow_api_url_edit)
        self.redcap_token_input = QLineEdit("")
        self.redcap_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.detected_project_value = QLabel("-")
        self.detected_project_value.setWordWrap(True)
        self.saved_redcap_projects_combo = QComboBox()
        self.saved_redcap_projects_combo.currentIndexChanged.connect(self.select_saved_redcap_project)
        redcap_form.addRow(tr("redcap_api_url", self.language), self.redcap_url_input)
        redcap_form.addRow(tr("redcap_api_token", self.language), self.redcap_token_input)
        redcap_form.addRow(tr("validated_project", self.language), self.detected_project_value)
        redcap_form.addRow(tr("saved_redcap_projects", self.language), self.saved_redcap_projects_combo)
        redcap_layout.addLayout(redcap_form)

        redcap_buttons = QHBoxLayout()
        self.add_redcap_token_button = QPushButton(tr("add_redcap_token", self.language))
        self.add_redcap_token_button.setProperty("secondary", True)
        self.add_redcap_token_button.clicked.connect(self.prepare_new_token)
        self.fetch_redcap_projects_button = QPushButton(tr("fetch_projects", self.language))
        self.fetch_redcap_projects_button.setProperty("secondary", True)
        self.fetch_redcap_projects_button.clicked.connect(self.fetch_redcap_project)
        self.save_redcap_button = QPushButton(tr("save_redcap", self.language))
        self.save_redcap_button.clicked.connect(self.save_redcap_settings)
        redcap_buttons.addWidget(self.add_redcap_token_button)
        redcap_buttons.addWidget(self.fetch_redcap_projects_button)
        redcap_buttons.addWidget(self.save_redcap_button)
        redcap_layout.addLayout(redcap_buttons)

        self.redcap_status = QLabel("")
        self.redcap_status.setObjectName("MutedLabel")
        self.redcap_status.setWordWrap(True)
        redcap_layout.addWidget(self.redcap_status)
        panels_row.addWidget(redcap_card, 1)

        root.addLayout(panels_row)
        self.populate_saved_redcap_projects()
        if runtime.settings.redcap.selected_project_id:
            self.select_saved_redcap_project()
        self.update_provider_fields_visibility()

    def save_inference_settings(self) -> None:
        settings = self.runtime.settings
        settings.ui.language = self.language_combo.currentData()
        settings.inference.mode = "manual"
        settings.inference.selected_provider = self.provider_combo.currentData()
        settings.inference.local_ollama_base_url = self.local_url_input.text().strip() or "http://127.0.0.1:11434"
        settings.inference.remote_ollama_base_url = self._normalize_optional(self.remote_url_input.text())
        settings.inference.openai_compatible_base_url = self._normalize_optional(self.api_url_input.text())
        settings.inference.openai_compatible_model = self._normalize_optional(self.api_model_input.text())
        api_key = self.api_key_input.text().strip()
        if settings.inference.selected_provider == "openai_compatible" and api_key:
            self.runtime.secrets_store.set(settings.inference.api_key_secret_name, api_key)
            self.api_key_input.clear()
            self.api_key_input.setPlaceholderText(tr("api_key_saved_placeholder", settings.ui.language))
        self.runtime.settings_store.save(settings)
        self.provider_status.setText(tr("saved_inference", settings.ui.language))

    def update_provider_fields_visibility(self) -> None:
        provider = self.provider_combo.currentData()
        show_local = provider == "local_ollama"
        show_remote = provider == "remote_ollama"
        show_api = provider == "openai_compatible"

        self.local_url_label.setVisible(show_local)
        self.local_url_input.setVisible(show_local)
        self.remote_url_label.setVisible(show_remote)
        self.remote_url_input.setVisible(show_remote)
        self.api_url_label.setVisible(show_api)
        self.api_url_input.setVisible(show_api)
        self.api_model_label.setVisible(show_api)
        self.api_model_input.setVisible(show_api)
        self.api_key_label.setVisible(show_api)
        self.api_key_input.setVisible(show_api)

    def save_redcap_settings(self) -> None:
        settings = self.runtime.settings
        settings.ui.language = self.language_combo.currentData()
        settings.redcap.api_url = self.get_redcap_api_url()

        token = self.redcap_token_input.text().strip()
        if not settings.redcap.api_url or not token or self.validated_project is None:
            self.redcap_status.setText(tr("redcap_validate_before_save", self.language))
            return

        token_secret_name = self.build_redcap_token_secret_name(self.validated_project.project_id)
        self.runtime.secrets_store.set(token_secret_name, token)

        settings.redcap.selected_project_id = self.validated_project.project_id
        settings.redcap.selected_project_name = self.validated_project.project_title
        settings.redcap.selected_project_token_secret_name = token_secret_name
        self.upsert_saved_project_token(
            RedcapProjectToken(
                api_url=settings.redcap.api_url,
                project_id=self.validated_project.project_id,
                project_name=self.validated_project.project_title,
                token_secret_name=token_secret_name,
            )
        )
        if settings.inference.selected_provider:
            settings.first_run_completed = True
        self.runtime.settings_store.save(settings)
        self.populate_saved_redcap_projects()
        self.redcap_status.setText(
            tr("redcap_project_saved", settings.ui.language, project=self.validated_project.project_title)
        )

    def fetch_redcap_project(self) -> None:
        api_url = self.get_redcap_api_url()
        api_token = self.redcap_token_input.text().strip()
        if not api_url or not api_token:
            self.redcap_status.setText(tr("redcap_missing_credentials", self.language))
            return

        try:
            client = RedcapClient(api_url=api_url, api_token=api_token)
            project = client.get_project()
        except RedcapAPIError as exc:
            self.validated_project = None
            self.detected_project_value.setText("-")
            self.redcap_status.setText(str(exc))
            return
        except Exception as exc:
            self.validated_project = None
            self.detected_project_value.setText("-")
            self.redcap_status.setText(tr("config_load_error", self.language, error=str(exc)))
            return

        if project is None:
            self.validated_project = None
            self.detected_project_value.setText("-")
            self.redcap_status.setText(tr("redcap_no_projects", self.language))
            return

        self.validated_project = project
        self.detected_project_value.setText(project.project_title)
        self.redcap_status.setText(
            tr("redcap_project_validated", self.language, project=project.project_title)
        )

    def populate_saved_redcap_projects(self) -> None:
        settings = self.runtime.settings
        self.saved_redcap_projects_combo.blockSignals(True)
        self.saved_redcap_projects_combo.clear()
        self.saved_redcap_projects_combo.addItem(tr("redcap_saved_placeholder", self.language), None)
        for project in settings.redcap.saved_project_tokens:
            self.saved_redcap_projects_combo.addItem(project.project_name, project.project_id)
        if settings.redcap.selected_project_id:
            self._set_combo_value(self.saved_redcap_projects_combo, settings.redcap.selected_project_id)
        self.saved_redcap_projects_combo.blockSignals(False)

    def select_saved_redcap_project(self) -> None:
        selected_project_id = self.saved_redcap_projects_combo.currentData()
        if not selected_project_id:
            return
        settings = self.runtime.settings
        for project in settings.redcap.saved_project_tokens:
            if project.project_id != str(selected_project_id):
                continue
            settings.redcap.api_url = project.api_url
            settings.redcap.selected_project_id = project.project_id
            settings.redcap.selected_project_name = project.project_name
            settings.redcap.selected_project_token_secret_name = project.token_secret_name
            self.redcap_url_input.setText(project.api_url)
            token = self.runtime.secrets_store.get(project.token_secret_name, "") or ""
            self.redcap_token_input.setText(token)
            self.validated_project = RedcapProject(
                project_id=project.project_id,
                project_title=project.project_name,
            )
            self.detected_project_value.setText(project.project_name)
            self.runtime.settings_store.save(settings)
            self.redcap_status.setText(
                tr("redcap_project_selected", self.language, project=project.project_name)
            )
            return

    def prepare_new_token(self) -> None:
        self.saved_redcap_projects_combo.blockSignals(True)
        self.saved_redcap_projects_combo.setCurrentIndex(0)
        self.saved_redcap_projects_combo.blockSignals(False)
        self.redcap_token_input.clear()
        self.validated_project = None
        self.detected_project_value.setText("-")
        self.redcap_status.setText(tr("redcap_new_token_ready", self.language))

    def upsert_saved_project_token(self, project_token: RedcapProjectToken) -> None:
        settings = self.runtime.settings
        updated: list[RedcapProjectToken] = []
        replaced = False
        for existing in settings.redcap.saved_project_tokens:
            if existing.project_id == project_token.project_id and existing.api_url == project_token.api_url:
                updated.append(project_token)
                replaced = True
            else:
                updated.append(existing)
        if not replaced:
            updated.append(project_token)
        settings.redcap.saved_project_tokens = updated

    def get_redcap_api_url(self) -> str | None:
        if hasattr(self, "redcap_url_input") and self.redcap_url_input.isReadOnly():
            return self._normalize_optional(self.redcap_url_input.text()) or self._normalize_optional(
                self.runtime.app_config.get("redcap", {}).get("api_url", "")
            )
        if hasattr(self, "redcap_url_input"):
            return self._normalize_optional(self.redcap_url_input.text())
        return self._normalize_optional(self.runtime.app_config.get("redcap", {}).get("api_url", ""))

    @staticmethod
    def build_redcap_token_secret_name(project_id: str | None) -> str:
        if not project_id:
            return "redcap_api_token"
        return f"redcap_api_token_{project_id}"

    @staticmethod
    def _normalize_optional(value: str) -> str | None:
        value = str(value).strip()
        return value or None

    @staticmethod
    def _set_combo_value(combo, value: str | None) -> None:
        if value is None:
            return
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return
