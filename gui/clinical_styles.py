CLINICAL_STYLE = """
QWidget {
    background: #f6f4ef;
    color: #17202a;
    font-family: "Avenir Next", "Aptos", "Segoe UI", sans-serif;
    font-size: 14px;
}

QLabel {
    background: transparent;
}

QDialog {
    background: #f6f4ef;
}

QToolTip {
    background: #0f2027;
    color: #ffffff;
    border: 1px solid #315160;
    border-radius: 6px;
    padding: 6px 8px;
}

QMainWindow#ClinicalMainWindow {
    background: #f6f4ef;
}

QWidget#ClinicalContent {
    background: #f6f4ef;
}

QScrollArea#ClinicalPageScroll {
    background: transparent;
    border: none;
}

QWidget#ClinicalSidebar {
    background: #071923;
    border-right: 1px solid #071923;
}

QFrame#SidebarBrandBlock {
    background: transparent;
    border: none;
    padding-bottom: 6px;
}

QLabel#SidebarAppMark {
    background: #0b9488;
    color: #ffffff;
    border: 1px solid #3ed5c7;
    border-radius: 8px;
    min-width: 38px;
    max-width: 38px;
    min-height: 38px;
    max-height: 38px;
    font-size: 11px;
    font-weight: 850;
}

QLabel#SidebarVersionHint {
    color: #8ca6b3;
    font-size: 11px;
    font-weight: 650;
}

QFrame#TopBand, QFrame#PageHeader {
    background: #fffdf9;
    border: 1px solid #e3ded5;
    border-radius: 8px;
}

QFrame#WorkflowCard, QFrame#ConnectionPanel, QFrame#InfoPanel, QFrame#WizardPanel, QFrame#GuidancePanel, QFrame#PanelCard, QFrame#HeroCard {
    background: #fffdf9;
    border: 1px solid #e3ded5;
    border-radius: 8px;
}

QFrame#DashboardHeader {
    background: #fffdf9;
    border: 1px solid #e3ded5;
    border-radius: 10px;
}

QFrame#DashboardContextCard {
    background: #f1fbf8;
    border: 1px solid #b9e4dc;
    border-radius: 9px;
    min-width: 250px;
}

QLabel#DashboardEyebrow {
    color: #0b746b;
    font-size: 12px;
    font-weight: 820;
}

QFrame#DashboardMetricCard {
    background: #fffdf9;
    border: 1px solid #e3ded5;
    border-radius: 9px;
    min-height: 88px;
}

QLabel#DashboardMetricCaption {
    color: #526272;
    font-size: 12px;
    font-weight: 750;
}

QLabel#DashboardMetricValue {
    color: #111827;
    font-size: 26px;
    font-weight: 840;
}

QLabel#DashboardMetricNote {
    color: #7a8795;
    font-size: 12px;
}

QLabel#DashboardSectionTitle {
    color: #17202a;
    font-size: 14px;
    font-weight: 820;
}

QFrame#DashboardActionCard {
    background: #fffdf9;
    border: 1px solid #e3ded5;
    border-radius: 10px;
    min-height: 150px;
}

QFrame#DashboardActionCard:hover {
    background: #ffffff;
    border: 1px solid #b7dfd5;
}

QLabel#DashboardActionBadge {
    background: #e6f7f3;
    color: #0b746b;
    border: 1px solid #b7dfd5;
    border-radius: 8px;
    min-width: 34px;
    max-width: 34px;
    min-height: 34px;
    max-height: 34px;
    font-size: 12px;
    font-weight: 840;
}

QLabel#DashboardActionTitle {
    color: #17202a;
    font-size: 15px;
    font-weight: 820;
}

QLabel#DashboardActionBody {
    color: #667789;
    font-size: 12px;
}

QPushButton#DashboardActionButton {
    background: transparent;
    color: #0b746b;
    border: 1px solid transparent;
    padding: 6px 2px;
    text-align: left;
    font-weight: 800;
}

QPushButton#DashboardActionButton:hover {
    background: #edf8f4;
    border: 1px solid #b7dfd5;
}

QFrame#DashboardPanel {
    background: #fffdf9;
    border: 1px solid #e3ded5;
    border-radius: 10px;
}

QFrame#DashboardStatusRow {
    background: transparent;
    border-bottom: 1px solid #eee9e1;
    min-height: 28px;
}

QLabel#DashboardStatusLabel {
    color: #667789;
    font-size: 12px;
}

QLabel#DashboardStatusValue {
    color: #0b746b;
    font-size: 12px;
    font-weight: 780;
}

QFrame#WorkflowCard:hover {
    background: #ffffff;
    border: 1px solid #cddfd8;
}

QFrame#AccentStrip {
    background: #0b7a71;
    border-radius: 3px;
}

QFrame#Stepper {
    background: #fffdf9;
    border: 1px solid #e3ded5;
    border-radius: 8px;
}

QLabel#AppBrand {
    color: #ffffff;
    font-size: 21px;
    font-weight: 780;
    padding-bottom: 2px;
}

QLabel#PageTitle {
    color: #111827;
    font-size: 29px;
    font-weight: 780;
}

QLabel#TitleLabel {
    color: #111827;
    font-size: 24px;
    font-weight: 780;
}

QLabel#SectionTitle {
    color: #17202a;
    font-size: 16px;
    font-weight: 760;
}

QLabel#SectionEventTitle {
    color: #0f766e;
    font-size: 12px;
    font-weight: 760;
}

QLabel#SectionLabel {
    color: #18202a;
    font-size: 15px;
    font-weight: 720;
}

QLabel#MutedLabel {
    color: #667789;
}

QLabel#SmallMutedLabel {
    color: #a7b9c2;
}

QLabel#SmallMutedLabel {
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
    border: 1px solid #ded8cd;
    border-radius: 7px;
    padding: 8px 10px;
    font-weight: 650;
}

QLabel#WizardStepPill, QPushButton#WizardStepPill {
    background: #fbfaf6;
    color: #5f6f7d;
    border: 1px solid #e3ded5;
    border-radius: 7px;
    padding: 10px 13px;
    font-weight: 700;
    min-height: 22px;
    text-align: left;
}

QLabel#WizardStepPill[complete="true"], QPushButton#WizardStepPill[complete="true"] {
    background: #eef9f5;
    color: #0b7a71;
    border: 1px solid #b7dfd5;
}

QLabel#WizardStepPill[active="true"], QPushButton#WizardStepPill[active="true"] {
    background: #0f2027;
    color: #ffffff;
    border: 1px solid #0f2027;
}

QPushButton#WizardStepPill:disabled {
    background: #fbfaf6;
    color: #9aa8b4;
    border: 1px solid #e3ded5;
}

QLabel#StepNumber {
    color: #b66a16;
    font-size: 13px;
    font-weight: 800;
    letter-spacing: 0px;
}

QLabel#WizardStatus {
    background: #f8faf8;
    color: #394757;
    border: 1px solid #e4dfd8;
    border-left: 4px solid #d49a42;
    border-radius: 7px;
    padding: 11px 13px;
    font-weight: 600;
}

QLabel#StatusPill {
    background: #eef9f5;
    color: #0b746b;
    border: 1px solid #b7dfd5;
    border-radius: 8px;
    padding: 7px 11px;
    font-weight: 650;
}

QLabel#WarningPill {
    background: #fff6e9;
    color: #9d5a16;
    border: 1px solid #efcf9d;
    border-radius: 8px;
    padding: 7px 11px;
    font-weight: 650;
}

QLabel#UserContextPill {
    background: #ffffff;
    color: #334155;
    border: 1px solid #d8d5cc;
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12px;
    font-weight: 650;
}

QLabel#UserContextPillMuted {
    background: #f2f4f5;
    color: #72808d;
    border: 1px solid #e0ded7;
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12px;
    font-weight: 650;
}

QLabel#ProjectContextLabel {
    color: #667789;
    font-size: 12px;
    padding: 0 4px;
}

QPushButton {
    background: #0b7a71;
    color: #ffffff;
    border: none;
    border-radius: 7px;
    padding: 10px 15px;
    font-weight: 700;
    min-height: 24px;
}

QPushButton:hover {
    background: #0f8f84;
}

QPushButton:disabled {
    background: #d7dde2;
    color: #f8fafc;
}

QPushButton[secondary="true"] {
    background: #f7f6f2;
    color: #23323f;
    border: 1px solid #ded8cd;
}

QPushButton[secondary="true"]:hover {
    background: #eeeae3;
}

QPushButton[nav="true"] {
    background: transparent;
    color: #d0dde3;
    border: 1px solid transparent;
    border-left: 4px solid transparent;
    text-align: left;
    padding: 10px 13px;
}

QPushButton[nav="true"][active="true"] {
    background: #18313a;
    color: #ffffff;
    border: 1px solid #315160;
    border-left: 4px solid #75d7c8;
}

QPushButton[quiet="true"] {
    background: transparent;
    color: #0f766e;
    border: 1px solid #b8e4dc;
}

QPushButton[tab="true"] {
    background: #fffdf9;
    color: #435261;
    border: 1px solid #ddd7cc;
    padding: 10px 16px;
}

QPushButton[tab="true"][active="true"] {
    background: #0f2027;
    color: #ffffff;
    border: 1px solid #0f2027;
}

QLineEdit, QComboBox, QDateEdit {
    background: #ffffff;
    border: 1px solid #ddd8cf;
    border-radius: 7px;
    padding: 9px 11px;
    min-height: 22px;
    selection-background-color: #b9e4dc;
}

QLineEdit:focus, QComboBox:focus, QDateEdit:focus {
    border: 1px solid #0b7a71;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background: #ffffff;
    color: #17202a;
    border: 1px solid #ded8cd;
    border-radius: 7px;
    padding: 6px;
    selection-background-color: #e8f6f2;
    selection-color: #17202a;
}

QCheckBox {
    color: #344454;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 17px;
    height: 17px;
    border-radius: 4px;
    border: 1px solid #cfc8bc;
    background: #ffffff;
}

QCheckBox::indicator:checked {
    background: #0b7a71;
    border: 1px solid #0b7a71;
}

QFrame#DataEntryDateEdit {
    background: transparent;
    border: none;
}

QLineEdit#DataEntryDateLineEdit {
    min-height: 22px;
}

QComboBox#SidebarProjectCombo {
    background: #edf8f4;
    color: #0b746b;
    border: 1px solid #b7dfd5;
    border-radius: 8px;
    padding: 8px 10px;
    font-weight: 650;
}

QComboBox#SidebarProjectCombo:disabled {
    background: #fff5e5;
    color: #9a5718;
    border: 1px solid #f1cf9d;
}

QComboBox#DagSwitchCombo {
    background: #ffffff;
    color: #20303b;
    border: 1px solid #b7dfd5;
    border-radius: 8px;
    padding: 6px 9px;
    min-height: 22px;
    font-size: 12px;
    font-weight: 650;
}

QFrame#DataEntryActivityPanel {
    background: #fffdf9;
    border: 1px solid #e3ded5;
    border-radius: 8px;
}

QFrame#DataEntryActivityPanel[tone="running"] {
    background: #f4fbf9;
    border: 1px solid #b7ded5;
}

QFrame#DataEntryActivityPanel[tone="success"] {
    background: #edf8f4;
    border: 1px solid #a9d9cf;
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
    background: #fffdf9;
    border: 1px solid #e3ded5;
    border-radius: 10px;
}

QFrame#DataEntryWorkspaceShell {
    background: #fffdf9;
    border: 1px solid #e3ded5;
    border-radius: 10px;
}

QLabel#DataEntryActivityMarker {
    background: #8ca0ad;
    border-radius: 4px;
}

QLabel#DataEntryActivityMarker[tone="running"] {
    background: #0b7a71;
}

QLabel#DataEntryActivityMarker[tone="success"] {
    background: #0b7a71;
}

QLabel#DataEntryActivityMarker[tone="warning"] {
    background: #c57a1c;
}

QLabel#DataEntryActivityMarker[tone="error"] {
    background: #b42318;
}

QLabel#DataEntryActivityTitle {
    color: #20303b;
    font-size: 13px;
    font-weight: 760;
}

QLabel#DataEntryActivityDetail {
    color: #607080;
    font-size: 12px;
}

QListWidget, QPlainTextEdit, QTableWidget {
    background: #ffffff;
    border: 1px solid #ded8cd;
    border-radius: 8px;
    padding: 6px;
    selection-background-color: #e8f6f2;
    selection-color: #17202a;
}

QListWidget::item {
    padding: 7px 8px;
    border-radius: 6px;
}

QListWidget::item:selected {
    background: #e8f6f2;
    color: #0b746b;
}

QTableWidget::item {
    padding: 6px;
}

QTableWidget::item:selected {
    background: #e8f6f2;
    color: #17202a;
}

QTableWidget#ExcelMappingTable {
    background: #ffffff;
    alternate-background-color: #fcfbf8;
    border: 1px solid #ded8cd;
    border-radius: 8px;
    gridline-color: #f0ebe4;
    selection-background-color: #e8f6f2;
    selection-color: #18202a;
}

QTableWidget#ExcelMappingTable QComboBox {
    padding: 7px 9px;
    min-height: 22px;
}

QListWidget#WizardQueueList {
    background: #fcfbf8;
    border: 1px solid #e0ded7;
    border-radius: 8px;
    padding: 8px;
}

QListWidget#DataEntryRecordList {
    background: #ffffff;
    border: 1px solid #e0dad1;
    border-radius: 8px;
    padding: 8px;
    min-width: 260px;
}

QListWidget#DataEntryRecordList::item {
    padding: 10px 11px;
    border-radius: 6px;
}

QListWidget#DataEntryRecordList::item:selected {
    background: #e8f6f2;
    color: #0b746b;
}

QWidget#DataEntryForm {
    background: transparent;
}

QFrame#DataEntryFormHeader {
    background: #fffdf9;
    border: 1px solid #e3ded5;
    border-radius: 8px;
}

QFrame#DataEntryFormShell {
    background: transparent;
}

QScrollArea#DataEntrySectionScroll {
    background: transparent;
    border: none;
}

QScrollArea#DataEntryFormNavScroll {
    background: #fffdf9;
    border: 1px solid #e0ded7;
    border-radius: 8px;
}

QWidget#DataEntryFormNav {
    background: #fffdf9;
}

QLabel#DataEntryFormNavEvent {
    color: #5e6d7b;
    font-size: 12px;
    font-weight: 780;
    padding: 8px 6px 4px 6px;
}

QFrame#DataEntryFormNavButton {
    background: #fffdf9;
    border: 1px solid transparent;
    border-radius: 7px;
}

QLabel#DataEntryFormNavButtonLabel {
    color: #334155;
    font-weight: 650;
}

QFrame#DataEntryFormNavButton:hover {
    background: #edf8f4;
}

QFrame#DataEntryFormNavButton:hover QLabel#DataEntryFormNavButtonLabel {
    color: #0b746b;
}

QFrame#DataEntryFormNavButton[active="true"] {
    background: #0f2027;
    border: 1px solid #0f2027;
}

QFrame#DataEntryFormNavButton[active="true"] QLabel#DataEntryFormNavButtonLabel {
    color: #ffffff;
}

QFrame#DataEntryFormNavButtonRow {
    background: transparent;
}

QFrame#DataEntryFormNavEventRow {
    background: transparent;
    border-top: 1px solid #ece7df;
    padding-top: 4px;
}

QToolButton#DataEntryFormNavInlineAdd {
    background: #edf8f4;
    color: #0b746b;
    border: 1px solid #b7dfd5;
    border-radius: 14px;
    padding: 0;
    margin: 0;
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
    font-size: 17px;
    font-weight: 820;
}

QToolButton#DataEntryFormNavInlineAdd:hover {
    background: #dff4ee;
    border: 1px solid #8fcfc2;
}

QToolButton#DataEntryFormNavEventAdd {
    background: #0f2027;
    color: #ffffff;
    border: 1px solid #0f2027;
    border-radius: 14px;
    padding: 0;
    margin: 0;
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
    font-size: 17px;
    font-weight: 820;
}

QToolButton#DataEntryFormNavEventAdd:hover {
    background: #0b7a71;
    border: 1px solid #0b7a71;
}

QStackedWidget#DataEntryFormStack {
    background: transparent;
}

QLabel#DataEntryRecordTitle {
    color: #111827;
    font-size: 21px;
    font-weight: 760;
}

QFrame#DataEntryFormSection {
    background: #fffdf9;
    border: 1px solid #e0ded7;
    border-radius: 8px;
}

QFrame#DataEntryFieldRow {
    background: #ffffff;
    border: 1px solid #ece7df;
    border-left: 4px solid #d8d5cc;
    border-radius: 8px;
    padding: 9px 10px;
}

QFrame#DataEntryFieldRow[field_state="filled"] {
    background: #f1fbf7;
    border: 1px solid #c9e9df;
    border-left: 4px solid #0b7a71;
}

QFrame#DataEntryFieldRow[field_state="required_missing"] {
    background: #fff7ed;
    border: 1px solid #f1cf9d;
    border-left: 4px solid #b56a19;
}

QFrame#DataEntryFieldRow[field_state="info"] {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-left: 4px solid #94a3b8;
}

QLabel#DataEntryFieldLabel {
    color: #18202a;
    font-weight: 700;
}

QFrame#DataEntryFormSubsectionBlock {
    background: #f7fbf8;
    border: 1px solid #dbe8e2;
    border-left: 4px solid #0b7a71;
    border-radius: 8px;
}

QLabel#DataEntryFormSubsectionTitle {
    color: #0b5e57;
    font-size: 14px;
    font-weight: 820;
    padding: 0 0 4px 0;
}

QLabel#DataEntryFieldState {
    background: #f2f4f5;
    color: #607080;
    border: 1px solid #e0ded7;
    border-radius: 999px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 750;
}

QLabel#DataEntryFieldState[state="filled"] {
    background: #dcf7ed;
    color: #0b746b;
    border: 1px solid #b7dfd5;
}

QLabel#DataEntryFieldState[state="required_missing"] {
    background: #fff0d8;
    color: #9a5718;
    border: 1px solid #f1cf9d;
}

QLabel#DataEntryFieldState[state="info"] {
    background: #eef2f7;
    color: #536273;
    border: 1px solid #d8dee8;
}

QLabel#DataEntryFieldNote, QLabel#DataEntryBranchingLogic {
    color: #607080;
    font-size: 12px;
}

QLabel#DataEntryReadonlyValue {
    background: #f8fafc;
    color: #334155;
    border: 1px solid #e0ded7;
    border-radius: 7px;
    padding: 9px 10px;
}

QLabel#DataEntryReadonlyValue[calculated="true"] {
    background: #eefaf6;
    color: #0b746b;
    border: 1px solid #b7dfd5;
    font-weight: 760;
}

QFrame#DataEntryChoiceGroup {
    background: transparent;
}

QToolButton#DataEntryClearRadioButton {
    background: transparent;
    color: #0b746b;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 3px 6px;
    font-size: 12px;
    font-weight: 720;
}

QToolButton#DataEntryClearRadioButton:hover {
    background: #edf8f4;
    border: 1px solid #b7dfd5;
}

QToolButton#DataEntryClearRadioButton:disabled {
    color: #9db0bc;
    background: transparent;
    border: 1px solid transparent;
}

QHeaderView::section {
    background: #ede8df;
    color: #334155;
    border: none;
    border-bottom: 1px solid #ded8cd;
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
    background: #0b7a71;
    border-radius: 6px;
}

QSplitter::handle {
    background: #e4dfd8;
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
    background: #cfc8bc;
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
    background: #cfc8bc;
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
"""
