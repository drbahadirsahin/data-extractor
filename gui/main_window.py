from __future__ import annotations

from runtime_context import RuntimeContext
from gui.i18n import tr
from gui.view_models import get_initial_page_index


class MainWindow:
    def __init__(self, runtime: RuntimeContext) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QHBoxLayout,
            QLabel,
            QMainWindow,
            QPushButton,
            QStackedWidget,
            QVBoxLayout,
            QWidget,
        )

        self.runtime = runtime
        self.language = runtime.settings.ui.language
        self._window = QMainWindow()
        self._window.setWindowTitle(tr("app_title", self.language))
        self._window.resize(
            runtime.settings.ui.window_width,
            runtime.settings.ui.window_height,
        )

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(18)

        nav = QWidget()
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(12)

        title = QLabel(tr("app_title", self.language))
        title.setObjectName("TitleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        nav_layout.addWidget(title)

        subtitle = QLabel(tr("app_subtitle", self.language))
        subtitle.setObjectName("MutedLabel")
        nav_layout.addWidget(subtitle)

        self.onboarding_button = QPushButton(tr("nav_onboarding", self.language))
        self.workspace_button = QPushButton(tr("nav_workspace", self.language))
        self.workspace_button.setProperty("secondary", True)
        nav_layout.addWidget(self.onboarding_button)
        nav_layout.addWidget(self.workspace_button)
        nav_layout.addStretch(1)

        self.stack = QStackedWidget()

        from gui.onboarding_page import OnboardingPage
        from gui.workspace_page import WorkspacePage

        self.onboarding_page = OnboardingPage(runtime)
        self.workspace_page = WorkspacePage(runtime)
        self.stack.addWidget(self.onboarding_page.widget)
        self.stack.addWidget(self.workspace_page.widget)

        self.onboarding_button.clicked.connect(lambda: self.set_page(0))
        self.workspace_button.clicked.connect(lambda: self.set_page(1))

        layout.addWidget(nav, 0)
        layout.addWidget(self.stack, 1)
        self._window.setCentralWidget(central)
        self.set_page(get_initial_page_index(runtime))

    def set_page(self, index: int) -> None:
        if index == 1:
            self.workspace_page.refresh_redcap_projects()
        self.stack.setCurrentIndex(index)
        self.onboarding_button.setProperty("secondary", index != 0)
        self.workspace_button.setProperty("secondary", index != 1)
        self.onboarding_button.style().unpolish(self.onboarding_button)
        self.onboarding_button.style().polish(self.onboarding_button)
        self.workspace_button.style().unpolish(self.workspace_button)
        self.workspace_button.style().polish(self.workspace_button)

    def show(self) -> None:
        self._window.show()
