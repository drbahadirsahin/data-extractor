from pathlib import Path


CLINICAL_COMBO_POPUP_STYLE = """
QListView {
    background: #ffffff;
    alternate-background-color: #ffffff;
    color: #0f172a;
    border: none;
    border-radius: 7px;
    padding: 4px;
    outline: none;
    show-decoration-selected: 1;
}

QListView::item {
    background: #ffffff;
    color: #0f172a;
    border: none;
    border-radius: 5px;
    min-height: 30px;
    padding: 0 10px;
}

QListView::item:hover {
    background: #f0fdfa;
    color: #0f172a;
}

QListView::item:selected,
QListView::item:selected:active,
QListView::item:selected:!active {
    background: #ccfbf1;
    color: #0f172a;
    border-left: 3px solid #0d9488;
    padding-left: 7px;
}

QScrollBar:vertical {
    background: transparent;
    width: 9px;
    margin: 4px 2px;
}

QScrollBar::handle:vertical {
    background: #cbd5e1;
    border-radius: 4px;
    min-height: 24px;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
    border: none;
    height: 0;
}
"""


CLINICAL_COMBO_POPUP_CONTAINER_STYLE = """
QFrame#ClinicalComboPopupContainer {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 0;
}
"""


CLINICAL_CALENDAR_MENU_STYLE = """
QMenu#DataEntryDateMenu {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 11px;
    padding: 8px;
}

QMenu#DataEntryDateMenu::item {
    background: transparent;
    border: none;
    margin: 0;
    padding: 0;
}

QMenu#DataEntryDateMenu::item:selected {
    background: transparent;
}
"""


CLINICAL_CALENDAR_STYLE = """
QCalendarWidget#DataEntryCalendar {
    background: #ffffff;
    color: #0f172a;
    border: none;
}

QCalendarWidget#DataEntryCalendar QWidget {
    background: #ffffff;
    color: #0f172a;
}

QCalendarWidget#DataEntryCalendar QWidget#qt_calendar_navigationbar {
    background: #f0fdfa;
    border: none;
    border-bottom: 1px solid #ccfbf1;
    min-height: 42px;
}

QCalendarWidget#DataEntryCalendar QToolButton {
    background: transparent;
    color: #0f172a;
    border: 1px solid transparent;
    border-radius: 7px;
    min-height: 28px;
    padding: 3px 8px;
    font-weight: 700;
}

QCalendarWidget#DataEntryCalendar QToolButton:hover,
QCalendarWidget#DataEntryCalendar QToolButton:pressed {
    background: #ccfbf1;
    color: #0f766e;
    border: 1px solid #99f6e4;
}

QCalendarWidget#DataEntryCalendar QToolButton#qt_calendar_prevmonth,
QCalendarWidget#DataEntryCalendar QToolButton#qt_calendar_nextmonth {
    min-width: 30px;
    max-width: 30px;
    padding: 2px;
}

QCalendarWidget#DataEntryCalendar QSpinBox {
    background: #ffffff;
    color: #0f172a;
    border: 1px solid #99e2d8;
    border-radius: 6px;
    min-height: 30px;
    padding: 3px 28px 3px 8px;
    selection-background-color: #ccfbf1;
    selection-color: #0f172a;
}

QCalendarWidget#DataEntryCalendar QToolButton#DataEntryCalendarYearUp,
QCalendarWidget#DataEntryCalendar QToolButton#DataEntryCalendarYearDown {
    background: #f0fdfa;
    color: #0f766e;
    border: none;
    border-left: 1px solid #99e2d8;
    border-radius: 0;
    min-width: 0;
    min-height: 0;
    padding: 0;
    font-size: 8px;
    font-weight: 800;
}

QCalendarWidget#DataEntryCalendar QToolButton#DataEntryCalendarYearUp {
    border-bottom: 1px solid #99e2d8;
    border-top-right-radius: 5px;
}

QCalendarWidget#DataEntryCalendar QToolButton#DataEntryCalendarYearDown {
    border-bottom-right-radius: 5px;
}

QCalendarWidget#DataEntryCalendar QToolButton#DataEntryCalendarYearUp:hover,
QCalendarWidget#DataEntryCalendar QToolButton#DataEntryCalendarYearDown:hover,
QCalendarWidget#DataEntryCalendar QToolButton#DataEntryCalendarYearUp:pressed,
QCalendarWidget#DataEntryCalendar QToolButton#DataEntryCalendarYearDown:pressed {
    background: #ccfbf1;
    color: #0d9488;
    border-left: 1px solid #5eead4;
}

QCalendarWidget#DataEntryCalendar QAbstractItemView:enabled {
    background: #ffffff;
    alternate-background-color: #ffffff;
    color: #334155;
    border: none;
    outline: none;
    selection-background-color: #0d9488;
    selection-color: #ffffff;
    gridline-color: #e2e8f0;
}

QCalendarWidget#DataEntryCalendar QAbstractItemView:disabled {
    background: #ffffff;
    color: #94a3b8;
}

QCalendarWidget#DataEntryCalendar QMenu {
    background: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 5px;
}

QCalendarWidget#DataEntryCalendar QMenu::item {
    background: #ffffff;
    color: #0f172a;
    border-radius: 5px;
    padding: 6px 16px;
}

QCalendarWidget#DataEntryCalendar QMenu::item:selected {
    background: #ccfbf1;
    color: #0f766e;
}
"""


CLINICAL_OVERRIDE_NUMBER_STYLE = """
QFrame#OverrideNumberInput {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 7px;
}

QFrame#OverrideNumberInput:disabled {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
}

QSpinBox#OverrideNumberSpinBox {
    background: #ffffff;
    color: #0f172a;
    border: none;
    border-radius: 6px 0 0 6px;
    padding: 0 9px;
    min-height: 34px;
    selection-background-color: #ccfbf1;
    selection-color: #0f172a;
}

QSpinBox#OverrideNumberSpinBox:focus {
    background: #ffffff;
    color: #0f172a;
}

QSpinBox#OverrideNumberSpinBox:disabled {
    background: #f8fafc;
    color: #64748b;
}

QSpinBox#OverrideNumberSpinBox QLineEdit,
QLineEdit#OverrideNumberLineEdit {
    background: transparent;
    color: #0f172a;
    border: none;
    border-radius: 0;
    padding: 0;
    min-height: 0;
    selection-background-color: #ccfbf1;
    selection-color: #0f172a;
}

QSpinBox#OverrideNumberSpinBox QLineEdit:disabled,
QLineEdit#OverrideNumberLineEdit:disabled {
    background: transparent;
    color: #64748b;
}

QFrame#OverrideNumberStepButtons {
    background: transparent;
    border: none;
}

QToolButton#OverrideNumberStepUp,
QToolButton#OverrideNumberStepDown {
    background: #f0fdfa;
    color: #0f766e;
    border: none;
    border-left: 1px solid #99e2d8;
    border-radius: 0;
    padding: 0;
    margin: 0;
    min-width: 28px;
    min-height: 16px;
    font-size: 8px;
    font-weight: 800;
}

QToolButton#OverrideNumberStepUp {
    border-bottom: 1px solid #99e2d8;
    border-top-right-radius: 6px;
}

QToolButton#OverrideNumberStepDown {
    border-bottom-right-radius: 6px;
}

QToolButton#OverrideNumberStepUp:hover,
QToolButton#OverrideNumberStepDown:hover,
QToolButton#OverrideNumberStepUp:pressed,
QToolButton#OverrideNumberStepDown:pressed {
    background: #ccfbf1;
    color: #0d9488;
}

QToolButton#OverrideNumberStepUp:disabled,
QToolButton#OverrideNumberStepDown:disabled {
    background: #f8fafc;
    color: #94a3b8;
    border-left: 1px solid #e2e8f0;
}

QToolButton#OverrideNumberStepUp:disabled {
    border-bottom: 1px solid #e2e8f0;
}
"""


CLINICAL_STYLE = """
QWidget {
    color: #0f172a;
    font-family: "Inter", "SF Pro Text", "Segoe UI", "Helvetica Neue";
    font-size: 13px;
}

QLabel {
    background: transparent;
}

QDialog {
    background: #f8fafc;
}

QToolTip {
    background: #0f2027;
    color: #ffffff;
    border: 1px solid #315160;
    border-radius: 6px;
    padding: 6px 8px;
}

QMainWindow#ClinicalMainWindow {
    background: #f8fafc;
}

QWidget#ClinicalContent {
    background: #f8fafc;
}

QScrollArea#ClinicalPageScroll {
    background: #f8fafc;
    border: none;
}

QWidget#ClinicalPageViewport,
QWidget[clinicalPage="true"],
QStackedWidget {
    background: #f8fafc;
}

QFrame#GlobalContextBar {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 9px;
    min-height: 40px;
    max-height: 46px;
}

QLabel#GlobalPageTitle {
    color: #0f172a;
    font-size: 14px;
    font-weight: 700;
}

QLabel#GlobalContextCaption {
    color: #64748b;
    font-size: 11px;
    font-weight: 500;
}

QLabel#GlobalContextValue {
    color: #0f172a;
    font-size: 12px;
    font-weight: 600;
}

QLabel#GlobalContextSeparator {
    background: #e2e8f0;
    min-width: 1px;
    max-width: 1px;
    min-height: 22px;
    max-height: 22px;
}

QLabel#GlobalConnectionIndicator {
    color: #94a3b8;
    font-size: 11px;
    min-width: 16px;
}

QLabel#GlobalConnectionIndicator[connected="true"] {
    color: #16a34a;
}

QWidget#ClinicalSidebar {
    background: #082235;
    border-right: 1px solid #0b2b40;
}

QFrame#SidebarBrandBlock {
    background: transparent;
    border: none;
    padding-bottom: 6px;
}

QLabel#SidebarAppMark {
    background: #0d9488;
    color: #ffffff;
    border: 1px solid #2dd4bf;
    border-radius: 8px;
    min-width: 34px;
    max-width: 34px;
    min-height: 34px;
    max-height: 34px;
}

QLabel#SidebarVersionHint {
    color: #8aa3b2;
    font-size: 11px;
    font-weight: 600;
}

QFrame#TopBand, QFrame#PageHeader {
    background: transparent;
    border: none;
}

QFrame#PageContextCard {
    background: #f0fdfa;
    border: 1px solid #99e2d8;
    border-radius: 9px;
    min-width: 250px;
}

QFrame#WorkflowCard, QFrame#ConnectionPanel, QFrame#InfoPanel, QFrame#WizardPanel, QFrame#GuidancePanel, QFrame#PanelCard, QFrame#HeroCard {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
}

QFrame#ConnectionInnerCard {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 9px;
}

QLabel#ReadonlyInfoValue {
    background: #f8fafc;
    color: #0f172a;
    border: 1px solid #e2e8f0;
    border-radius: 7px;
    padding: 9px 10px;
    font-weight: 600;
}

QFrame#DashboardHeader {
    background: transparent;
    border: none;
}

QFrame#DashboardContextCard {
    background: #f0fdfa;
    border: 1px solid #99e2d8;
    border-radius: 9px;
    min-width: 250px;
}

QLabel#DashboardEyebrow {
    color: #0f766e;
    font-size: 12px;
    font-weight: 700;
}

QFrame#DashboardMetricCard {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    min-height: 80px;
}

QLabel#DashboardMetricCaption {
    color: #475569;
    font-size: 12px;
    font-weight: 600;
}

QLabel#DashboardMetricValue {
    color: #0f172a;
    font-size: 24px;
    font-weight: 700;
}

QLabel#DashboardMetricNote {
    color: #7a8795;
    font-size: 12px;
}

QLabel#DashboardSectionTitle {
    color: #0f172a;
    font-size: 14px;
    font-weight: 700;
}

QFrame#DashboardActionCard {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 9px;
    min-height: 132px;
}

QFrame#DashboardActionCard:hover {
    background: #ffffff;
    border: 1px solid #99e2d8;
}

QLabel#DashboardActionBadge {
    background: #ccfbf1;
    color: #0f766e;
    border: 1px solid #99f6e4;
    border-radius: 8px;
    min-width: 34px;
    max-width: 34px;
    min-height: 34px;
    max-height: 34px;
    font-size: 12px;
    font-weight: 700;
}

QLabel#DashboardActionTitle {
    color: #0f172a;
    font-size: 15px;
    font-weight: 700;
}

QLabel#DashboardActionBody {
    color: #64748b;
    font-size: 12px;
}

QPushButton#DashboardActionButton {
    background: transparent;
    color: #0f766e;
    border: 1px solid transparent;
    padding: 6px 2px;
    text-align: left;
    font-weight: 700;
}

QPushButton#DashboardActionButton:hover {
    background: #ecfdf5;
    border: 1px solid #99e2d8;
}

QFrame#DashboardPanel {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 9px;
}

QFrame#DashboardStatusRow {
    background: transparent;
    border-bottom: 1px solid #f1f5f9;
    min-height: 28px;
}

QLabel#DashboardStatusLabel {
    color: #64748b;
    font-size: 12px;
}

QLabel#DashboardStatusValue {
    color: #0f766e;
    font-size: 12px;
    font-weight: 700;
}

QFrame#WorkflowCard:hover {
    background: #ffffff;
    border: 1px solid #cddfd8;
}

QFrame#AccentStrip {
    background: #0d9488;
    border-radius: 3px;
}

QFrame#Stepper {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
}

QLabel#AppBrand {
    color: #ffffff;
    font-size: 15px;
    font-weight: 700;
    padding-bottom: 2px;
}

QLabel#PageTitle {
    color: #0f172a;
    font-size: 24px;
    font-weight: 700;
}

QLabel#TitleLabel {
    color: #0f172a;
    font-size: 24px;
    font-weight: 700;
}

QLabel#SectionTitle {
    color: #0f172a;
    font-size: 16px;
    font-weight: 600;
}

QLabel#SectionEventTitle {
    color: #0f766e;
    font-size: 12px;
    font-weight: 600;
}

QLabel#SectionLabel {
    color: #0f172a;
    font-size: 15px;
    font-weight: 600;
}

QLabel#MutedLabel {
    color: #64748b;
}

QLabel#SmallMutedLabel {
    color: #9fb4c1;
}

QLabel#SmallMutedLabel {
    font-size: 12px;
}

QLabel#SidebarSubtitle {
    color: #9fb4c1;
    font-size: 12px;
}

QLabel#VersionLabel {
    color: #9eb3bd;
    font-size: 12px;
    padding: 6px 2px 0 2px;
}

QLabel#StepLabel {
    background: #ffffff;
    color: #435261;
    border: 1px solid #e2e8f0;
    border-radius: 7px;
    padding: 8px 10px;
    font-weight: 600;
}

QPushButton#WizardStepCircle {
    background: #ffffff;
    color: #64748b;
    border: 1px solid #cbd5e1;
    border-radius: 14px;
    padding: 0;
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
    font-size: 12px;
    font-weight: 700;
}

QPushButton#WizardStepCircle[complete="true"] {
    background: #ecfdf5;
    color: #0f766e;
    border: 1px solid #5eead4;
}

QPushButton#WizardStepCircle[active="true"] {
    background: #0d9488;
    color: #ffffff;
    border: 1px solid #0d9488;
}

QPushButton#WizardStepCircle:disabled {
    background: #f8fafc;
    color: #94a3b8;
    border: 1px solid #e2e8f0;
}

QLabel#WizardStepCaption {
    color: #64748b;
    font-size: 11px;
    font-weight: 500;
}

QLabel#WizardStepCaption[active="true"] {
    color: #0f766e;
    font-weight: 700;
}

QLabel#WizardStepCaption[complete="true"] {
    color: #0f766e;
}

QFrame#WizardStepConnector {
    background: #e2e8f0;
    border: none;
}

QFrame#WizardStepConnector[complete="true"] {
    background: #5eead4;
}

QLabel#StepNumber {
    color: #b66a16;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0px;
}

QLabel#WizardStatus {
    background: #f8fafc;
    color: #394757;
    border: 1px solid #e2e8f0;
    border-left: 4px solid #d49a42;
    border-radius: 7px;
    padding: 11px 13px;
    font-weight: 600;
}

QLabel#StatusPill {
    background: #ecfdf5;
    color: #0f766e;
    border: 1px solid #99e2d8;
    border-radius: 8px;
    padding: 7px 11px;
    font-weight: 600;
}

QLabel#WarningPill {
    background: #fff6e9;
    color: #9d5a16;
    border: 1px solid #efcf9d;
    border-radius: 8px;
    padding: 7px 11px;
    font-weight: 600;
}

QLabel#UserContextPill {
    background: #ffffff;
    color: #334155;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12px;
    font-weight: 600;
}

QLabel#UserContextPillMuted {
    background: #f2f4f5;
    color: #72808d;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12px;
    font-weight: 600;
}

QLabel#ProjectContextLabel {
    color: #64748b;
    font-size: 12px;
    padding: 0 4px;
}

QPushButton {
    background: #0f766e;
    color: #ffffff;
    border: none;
    border-radius: 7px;
    padding: 10px 15px;
    font-weight: 700;
    min-height: 24px;
}

QPushButton:hover {
    background: #0d9488;
}

QPushButton:disabled {
    background: #d7dde2;
    color: #f8fafc;
}

QPushButton[secondary="true"] {
    background: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
}

QPushButton[secondary="true"]:hover {
    background: #f1f5f9;
}

QPushButton[secondary="true"]:disabled {
    background: #f8fafc;
    color: #94a3b8;
    border: 1px solid #e2e8f0;
}

QPushButton[nav="true"] {
    background: transparent;
    color: #c8d7df;
    border: 1px solid transparent;
    border-left: 3px solid transparent;
    border-radius: 8px;
    text-align: left;
    padding: 9px 12px;
    font-size: 13px;
    min-height: 22px;
}

QPushButton[nav="true"][active="true"] {
    background: #0d9488;
    color: #ffffff;
    border: 1px solid #0d9488;
    border-left: 3px solid #9ef0e4;
}

QPushButton[nav="true"]:hover {
    background: #102f3f;
    color: #ffffff;
    border: 1px solid #1d4051;
}

QPushButton[quiet="true"] {
    background: transparent;
    color: #0f766e;
    border: 1px solid #99e2d8;
}

QPushButton[quiet="true"]:disabled {
    background: #f8fafc;
    color: #94a3b8;
    border: 1px solid #e2e8f0;
}

QPushButton[compact="true"] {
    padding: 6px 10px;
    min-height: 20px;
}

QPushButton[tab="true"] {
    background: #ffffff;
    color: #435261;
    border: 1px solid #cbd5e1;
    padding: 10px 16px;
}

QPushButton[tab="true"][active="true"] {
    background: #0d9488;
    color: #ffffff;
    border: 1px solid #0d9488;
}

QPushButton#SourceModeButton {
    background: #ffffff;
    color: #334155;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 10px 16px;
    min-height: 32px;
    text-align: left;
}

QPushButton#SourceModeButton[active="true"] {
    background: #f0fdfa;
    color: #0f766e;
    border: 1px solid #0d9488;
}

QPushButton#SourceModeButton:hover {
    background: #f0fdfa;
    color: #0f766e;
    border: 1px solid #5eead4;
}

QLineEdit, QComboBox, QDateEdit {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 7px;
    padding: 9px 11px;
    min-height: 22px;
    selection-background-color: #b9e4dc;
}

QComboBox {
    padding-right: 30px;
}

QLineEdit:focus, QComboBox:focus, QDateEdit:focus {
    border: 1px solid #0d9488;
}

QComboBox QAbstractItemView {
    background: #ffffff;
    color: #0f172a;
    border: 1px solid #e2e8f0;
    border-radius: 7px;
    padding: 6px;
    selection-background-color: #ccfbf1;
    selection-color: #0f172a;
}

QCheckBox {
    color: #334155;
    spacing: 8px;
    min-height: 20px;
}

QCheckBox:hover {
    color: #0f172a;
}

QCheckBox:disabled {
    color: #94a3b8;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #cbd5e1;
    background: #ffffff;
}

QCheckBox::indicator:unchecked:hover {
    background: #f0fdfa;
    border: 1px solid #5eead4;
}

QCheckBox::indicator:unchecked:focus {
    border: 1px solid #0d9488;
}

QCheckBox::indicator:checked {
    background: #0d9488;
    border: 1px solid #0d9488;
    image: url("__CHECKBOX_CHECK_ICON__");
}

QCheckBox::indicator:checked:hover,
QCheckBox::indicator:checked:focus {
    background: #0f766e;
    border: 1px solid #0f766e;
}

QCheckBox::indicator:unchecked:disabled {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
}

QCheckBox::indicator:checked:disabled {
    background: #99cfc9;
    border: 1px solid #99cfc9;
    image: url("__CHECKBOX_CHECK_ICON__");
}

QRadioButton {
    color: #334155;
    spacing: 8px;
    min-height: 22px;
}

QRadioButton:hover {
    color: #0f172a;
}

QRadioButton:disabled {
    color: #94a3b8;
}

QRadioButton::indicator {
    width: 20px;
    height: 20px;
    background: transparent;
    border: none;
    image: url("__RADIO_UNCHECKED_ICON__");
}

QRadioButton::indicator:unchecked:hover,
QRadioButton::indicator:unchecked:focus {
    image: url("__RADIO_UNCHECKED_HOVER_ICON__");
}

QRadioButton::indicator:checked {
    image: url("__RADIO_CHECKED_ICON__");
}

QRadioButton::indicator:checked:hover,
QRadioButton::indicator:checked:focus {
    image: url("__RADIO_CHECKED_HOVER_ICON__");
}

QRadioButton::indicator:unchecked:disabled {
    image: url("__RADIO_DISABLED_ICON__");
}

QRadioButton::indicator:checked:disabled {
    image: url("__RADIO_CHECKED_DISABLED_ICON__");
}

QFrame#DataEntryDateEdit {
    background: transparent;
    border: none;
}

QLineEdit#DataEntryDateLineEdit {
    min-height: 22px;
    padding-right: 11px;
}

QToolButton#DataEntryDateButton {
    background: #ffffff;
    color: #0f766e;
    border: 1px solid #cbd5e1;
    border-radius: 7px;
    min-width: 38px;
    max-width: 38px;
    min-height: 38px;
    max-height: 38px;
    padding: 0;
}

QToolButton#DataEntryDateButton:hover,
QToolButton#DataEntryDateButton:focus {
    background: #f0fdfa;
    color: #0d9488;
    border: 1px solid #5eead4;
}

QToolButton#DataEntryDateButton:pressed {
    background: #ccfbf1;
    border: 1px solid #0d9488;
}

QToolButton#DataEntryDateButton:disabled {
    background: #f1f5f9;
    color: #94a3b8;
    border: 1px solid #e2e8f0;
}

QToolButton#DataEntryDateClearButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    min-width: 34px;
    max-width: 34px;
    min-height: 38px;
    max-height: 38px;
    padding: 0;
}

QToolButton#DataEntryDateClearButton:hover,
QToolButton#DataEntryDateClearButton:focus {
    background: #f8fafc;
    border: 1px solid #cbd5e1;
}

QToolButton#DataEntryDateClearButton:pressed {
    background: #eef2f7;
    border: 1px solid #94a3b8;
}

QToolButton#DataEntryDateClearButton:disabled {
    background: transparent;
    border: 1px solid transparent;
}

QComboBox#SidebarProjectCombo {
    background: #0d9488;
    color: #ffffff;
    border: 1px solid #17b0a3;
    border-radius: 9px;
    padding: 10px 11px;
    font-weight: 700;
    min-height: 28px;
}

QComboBox#GlobalProjectCombo, QComboBox#GlobalDagCombo {
    background: #f8fafc;
    color: #0f2027;
    border: 1px solid #e2e8f0;
    border-radius: 7px;
    padding: 4px 30px 4px 9px;
    min-height: 18px;
    font-size: 12px;
    font-weight: 600;
}

QComboBox#GlobalProjectCombo:focus, QComboBox#GlobalDagCombo:focus {
    border: 1px solid #0d9488;
}

QComboBox#GlobalProjectCombo:disabled, QComboBox#GlobalDagCombo:disabled {
    background: #f3f5f6;
    color: #83919f;
    border: 1px solid #e1e5e8;
}

QComboBox#SidebarProjectCombo:disabled {
    background: #fff3df;
    color: #9a5718;
    border: 1px solid #f1cf9d;
}

QComboBox#DagSwitchCombo {
    background: #ffffff;
    color: #0f172a;
    border: 1px solid #99e2d8;
    border-radius: 8px;
    padding: 6px 30px 6px 9px;
    min-height: 22px;
    font-size: 12px;
    font-weight: 600;
}

QFrame#DataEntryActivityPanel {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
}

QFrame#DataEntryActivityPanel[tone="running"] {
    background: #f4fbf9;
    border: 1px solid #99e2d8;
}

QFrame#DataEntryActivityPanel[tone="success"] {
    background: #ecfdf5;
    border: 1px solid #99e2d8;
}

QFrame#DataEntryActivityPanel[tone="warning"] {
    background: #fff8ec;
    border: 1px solid #efcf9d;
}

QFrame#DataEntryActivityPanel[tone="error"] {
    background: #fff1f0;
    border: 1px solid #efb8b0;
}

QFrame#DataEntryToolbar {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
}

QFrame#DataEntryWorkspaceShell {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
}

QLabel#DataEntryActivityMarker {
    background: #8ca0ad;
    border-radius: 4px;
}

QLabel#DataEntryActivityMarker[tone="running"] {
    background: #0d9488;
}

QLabel#DataEntryActivityMarker[tone="success"] {
    background: #0d9488;
}

QLabel#DataEntryActivityMarker[tone="warning"] {
    background: #c57a1c;
}

QLabel#DataEntryActivityMarker[tone="error"] {
    background: #b42318;
}

QLabel#DataEntryActivityTitle {
    color: #0f172a;
    font-size: 13px;
    font-weight: 600;
}

QLabel#DataEntryActivityDetail {
    color: #64748b;
    font-size: 12px;
}

QListWidget, QPlainTextEdit, QTableWidget {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 6px;
    selection-background-color: #ccfbf1;
    selection-color: #0f172a;
}

QListWidget::item {
    padding: 7px 8px;
    border-radius: 6px;
}

QListWidget::item:selected {
    background: #ccfbf1;
    color: #0f766e;
}

QTableWidget::item {
    padding: 6px;
}

QTableWidget::item:selected {
    background: #ccfbf1;
    color: #0f172a;
}

QTableWidget#ExcelMappingTable {
    background: #ffffff;
    alternate-background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    gridline-color: #eef2f7;
    selection-background-color: #ccfbf1;
    selection-color: #0f172a;
}

QTableWidget#ExcelMappingTable QComboBox {
    padding: 7px 9px;
    min-height: 22px;
}

QListWidget#WizardQueueList {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 8px;
}

QFrame#DocumentDropZone {
    background: #f8fafc;
    border: 1px dashed #94a3b8;
    border-radius: 8px;
    min-height: 50px;
}

QLabel#DocumentDropZoneIcon {
    background: #ccfbf1;
    border: 1px solid #99f6e4;
    border-radius: 20px;
    min-width: 32px;
    max-width: 32px;
    min-height: 32px;
    max-height: 32px;
}

QLabel#DocumentDropZoneTitle {
    color: #0f172a;
    font-weight: 700;
}

QFrame#InlineDraftCard {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
}

QLabel#InlineFieldLabel {
    color: #475569;
    font-size: 11px;
    font-weight: 600;
}

QListWidget#DocumentDraftList {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 7px;
    min-height: 54px;
    max-height: 72px;
}

QLabel#InlineDraftStatus {
    background: #f8fafc;
    color: #64748b;
    border: 1px solid #e2e8f0;
    border-radius: 7px;
    padding: 5px 8px;
    font-size: 12px;
}

QLabel#InlineQueueCount {
    background: #f0fdfa;
    color: #0f766e;
    border: 1px solid #99e2d8;
    border-radius: 8px;
    padding: 4px 8px;
    font-size: 11px;
    font-weight: 700;
}

QLabel#InlineDraftStatus[tone="success"] {
    background: #ecfdf5;
    color: #0f766e;
    border: 1px solid #99e2d8;
}

QLabel#InlineDraftStatus[tone="error"] {
    background: #fff1f0;
    color: #b42318;
    border: 1px solid #efb8b0;
}

QListWidget#DataEntryRecordList {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 8px;
    min-width: 190px;
    max-width: 240px;
}

QListWidget#DataEntryRecordList::item {
    padding: 10px 11px;
    border-radius: 6px;
}

QListWidget#DataEntryRecordList::item:selected {
    background: #ccfbf1;
    color: #0f766e;
}

QWidget#DataEntryForm {
    background: transparent;
}

QFrame#DataEntryFormEmpty {
    background: #f8fafc;
    border: 1px dashed #cbd5e1;
    border-radius: 8px;
}

QLabel#DataEntryFormEmptyTitle {
    color: #0f172a;
    font-size: 15px;
    font-weight: 700;
}

QFrame#DataEntryFormHeader {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
}

QFrame#DataEntryRecordHomeIntro,
QFrame#DataEntryRecordEditorToolbar {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
}

QLabel#DataEntryRecordHomeTitle {
    color: #0f172a;
    font-size: 14px;
    font-weight: 700;
}

QLabel#DataEntryRecordHomeBody {
    color: #64748b;
    font-size: 12px;
}

QLabel#DataEntryRecordHomeLegend {
    color: #94a3b8;
    font-size: 11px;
    font-weight: 600;
}

QLabel#DataEntryRecordHomeLegend[matrix_status="incomplete"] {
    color: #dc2626;
}

QLabel#DataEntryRecordHomeLegend[matrix_status="unverified"] {
    color: #d69a16;
}

QLabel#DataEntryRecordHomeLegend[matrix_status="filled"] {
    color: #0d9488;
}

QLabel#DataEntryRecordEditorContext {
    color: #334155;
    font-size: 12px;
    font-weight: 600;
}

QFrame#DataEntryFormShell {
    background: transparent;
}

QFrame#DataEntryEventNavPanel {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
}

QScrollArea#DataEntrySectionScroll {
    background: transparent;
    border: none;
}

QScrollArea#DataEntryFormNavScroll {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
}

QWidget#DataEntryFormNav {
    background: #ffffff;
}

QLabel#DataEntryFormNavEvent {
    color: #5e6d7b;
    font-size: 12px;
    font-weight: 700;
    padding: 8px 6px 4px 6px;
}

QFrame#DataEntryFormNavButton {
    background: #ffffff;
    border: 1px solid transparent;
    border-radius: 7px;
}

QLabel#DataEntryFormNavButtonLabel {
    color: #334155;
    font-weight: 600;
}

QFrame#DataEntryFormNavButton:hover {
    background: #ecfdf5;
}

QFrame#DataEntryFormNavButton:hover QLabel#DataEntryFormNavButtonLabel {
    color: #0f766e;
}

QFrame#DataEntryFormNavButton[active="true"] {
    background: #ccfbf1;
    border: 1px solid #99e2d8;
}

QFrame#DataEntryFormNavButton[active="true"] QLabel#DataEntryFormNavButtonLabel {
    color: #0f766e;
}

QFrame#DataEntryFormNavButtonRow {
    background: transparent;
}

QFrame#DataEntryFormNavEventRow {
    background: transparent;
    border-top: 1px solid #eef2f7;
    padding-top: 4px;
}

QStackedWidget#DataEntryFormStack {
    background: transparent;
}

QLabel#DataEntryRecordTitle {
    color: #0f172a;
    font-size: 21px;
    font-weight: 600;
}

QFrame#DataEntryFormSection {
    background: #ffffff;
    border: 1px solid #dce5eb;
    border-radius: 12px;
}

QFrame#DataEntryFormHeading {
    background: transparent;
    border: none;
    border-bottom: 1px solid #e2e8f0;
}

QFrame#DataEntryFormSection QLabel#SectionTitle {
    color: #0f172a;
    font-size: 20px;
    font-weight: 700;
}

QFrame#DataEntryFormSection QLabel#SectionEventTitle {
    color: #0f766e;
    font-size: 12px;
    font-weight: 700;
}

QLabel#DataEntryFormProgress {
    background: #fff7ed;
    color: #a65d12;
    border: 1px solid #fed7aa;
    border-radius: 8px;
    padding: 6px 9px;
    font-size: 11px;
    font-weight: 700;
}

QLabel#DataEntryFormProgress[complete="true"] {
    background: #ecfdf5;
    color: #0f766e;
    border: 1px solid #99e2d8;
}

QFrame#DataEntryFieldRow {
    background: transparent;
    border: 1px solid transparent;
    border-left: 3px solid transparent;
    border-radius: 8px;
}

QFrame#DataEntryFieldRow[field_state="filled"] {
    background: transparent;
    border: 1px solid transparent;
    border-left: 3px solid transparent;
}

QFrame#DataEntryFieldRow[field_state="required_missing"] {
    background: #fffaf4;
    border: 1px solid #fed7aa;
    border-left: 3px solid #d98922;
}

QFrame#DataEntryFieldRow[field_state="info"] {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-left: 3px solid #94a3b8;
}

QFrame#DataEntryFieldRow[conditional="true"] {
    background: #fbfbff;
    border: 1px solid #e4e4f4;
    border-left: 3px solid #8b8bb8;
}

QLabel#DataEntryFieldLabel {
    color: #0f172a;
    font-weight: 700;
}

QFrame#DataEntryFormSubsectionBlock {
    background: #f8fbfc;
    border: 1px solid #e2e8f0;
    border-left: 3px solid #99e2d8;
    border-radius: 10px;
}

QLabel#DataEntryFormSubsectionTitle {
    color: #0f766e;
    font-size: 15px;
    font-weight: 700;
    padding: 0 0 2px 0;
}

QLabel#DataEntryFieldState {
    background: #f2f4f5;
    color: #64748b;
    border: 1px solid #e2e8f0;
    border-radius: 999px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 600;
}

QLabel#DataEntryFieldState[state="filled"] {
    background: #dcf7ed;
    color: #0f766e;
    border: 1px solid #99e2d8;
}

QLabel#DataEntryFieldState[state="required_missing"] {
    background: transparent;
    color: #a65d12;
    border: none;
    padding: 2px 0;
}

QLabel#DataEntryFieldState[state="info"] {
    background: #eef2f7;
    color: #536273;
    border: 1px solid #d8dee8;
}

QLabel#DataEntryFieldNote {
    color: #64748b;
    font-size: 12px;
}

QLineEdit#DataEntryLineEdit,
QComboBox#DataEntryCombo,
QPlainTextEdit#DataEntryTextArea {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
}

QLineEdit#DataEntryLineEdit:focus,
QComboBox#DataEntryCombo:focus,
QPlainTextEdit#DataEntryTextArea:focus {
    background: #ffffff;
    border: 1px solid #0d9488;
}

QLineEdit#DataEntryLineEdit:read-only,
QPlainTextEdit#DataEntryTextArea:read-only {
    background: #f8fafc;
    color: #64748b;
    border: 1px solid #e2e8f0;
}

QLabel#DataEntryBranchingLogic {
    background: #f1f0ff;
    color: #63638c;
    border: 1px solid #dcdaf2;
    border-radius: 6px;
    padding: 4px 7px;
    font-size: 11px;
    font-weight: 700;
}

QLabel#DataEntryReadonlyValue {
    background: #f8fafc;
    color: #334155;
    border: 1px solid #e2e8f0;
    border-radius: 7px;
    padding: 9px 10px;
}

QLabel#DataEntryReadonlyValue[calculated="true"] {
    background: transparent;
    color: #0f766e;
    border: none;
    padding: 0;
    font-size: 18px;
    font-weight: 700;
}

QFrame#DataEntryCalculatedValue {
    background: #eefaf6;
    border: 1px solid #99e2d8;
    border-radius: 9px;
}

QLabel#DataEntryCalculatedHint {
    color: #0f766e;
    font-size: 11px;
    font-weight: 600;
}

QFrame#DataEntryChoiceGroup {
    background: transparent;
}

QFrame#DataEntryChoiceGroup QCheckBox,
QFrame#DataEntryChoiceGroup QRadioButton {
    padding: 2px 0;
}

QToolButton#DataEntryClearRadioButton {
    background: transparent;
    color: #0f766e;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 3px 6px;
    font-size: 12px;
    font-weight: 600;
}

QToolButton#DataEntryClearRadioButton:hover {
    background: #ecfdf5;
    border: 1px solid #99e2d8;
}

QToolButton#DataEntryClearRadioButton:disabled {
    color: #9db0bc;
    background: transparent;
    border: 1px solid transparent;
}

QHeaderView::section {
    background: #f1f5f9;
    color: #334155;
    border: none;
    border-bottom: 1px solid #e2e8f0;
    padding: 8px;
    font-weight: 700;
}

QProgressBar {
    background: #e2e8f0;
    border: 1px solid #cbd5e1;
    border-radius: 7px;
    text-align: center;
    min-height: 16px;
}

QProgressBar::chunk {
    background: #0d9488;
    border-radius: 6px;
}

QSplitter::handle {
    background: #e2e8f0;
}

QSplitter::handle:hover {
    background: #cddfd8;
}

QScrollBar:vertical {
    background: transparent;
    width: 12px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background: #cbd5e1;
    border-radius: 5px;
    min-height: 28px;
}

QScrollBar::handle:vertical:hover {
    background: #9fb7b0;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
    border: none;
}

QScrollBar:horizontal {
    background: transparent;
    height: 12px;
    margin: 2px;
}

QScrollBar::handle:horizontal {
    background: #cbd5e1;
    border-radius: 5px;
    min-width: 28px;
}

QScrollBar::handle:horizontal:hover {
    background: #9fb7b0;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: transparent;
    border: none;
}
""" + f"""
QComboBox::drop-down {{
    border: none;
    subcontrol-origin: border;
    subcontrol-position: center right;
    width: 28px;
}}

QComboBox::down-arrow {{
    image: url("{(Path(__file__).with_name('assets') / 'combo_chevron.svg').as_posix()}");
    width: 10px;
    height: 6px;
}}

QComboBox::down-arrow:on {{
    top: 1px;
}}
"""

CLINICAL_STYLE = CLINICAL_STYLE.replace(
    "__CHECKBOX_CHECK_ICON__",
    (Path(__file__).with_name("assets") / "checkbox_check.svg").as_posix(),
)

for _placeholder, _filename in {
    "__RADIO_UNCHECKED_ICON__": "radio_unchecked.svg",
    "__RADIO_UNCHECKED_HOVER_ICON__": "radio_unchecked_hover.svg",
    "__RADIO_CHECKED_ICON__": "radio_checked.svg",
    "__RADIO_CHECKED_HOVER_ICON__": "radio_checked_hover.svg",
    "__RADIO_DISABLED_ICON__": "radio_disabled.svg",
    "__RADIO_CHECKED_DISABLED_ICON__": "radio_checked_disabled.svg",
}.items():
    CLINICAL_STYLE = CLINICAL_STYLE.replace(
        _placeholder,
        (Path(__file__).with_name("assets") / _filename).as_posix(),
    )
