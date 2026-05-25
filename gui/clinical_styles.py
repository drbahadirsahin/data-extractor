CLINICAL_STYLE = """
QWidget {
    background: #f7f6f2;
    color: #18202a;
    font-family: "Inter", "Aptos", "Segoe UI", "Avenir Next", sans-serif;
    font-size: 14px;
}

QLabel {
    background: transparent;
}

QMainWindow#ClinicalMainWindow {
    background: #f7f6f2;
}

QWidget#ClinicalSidebar {
    background: #102027;
    border-right: 1px solid #102027;
}

QFrame#TopBand, QFrame#PageHeader {
    background: #ffffff;
    border: 1px solid #e0ded7;
    border-radius: 8px;
}

QFrame#WorkflowCard, QFrame#ConnectionPanel, QFrame#InfoPanel, QFrame#WizardPanel, QFrame#GuidancePanel, QFrame#PanelCard, QFrame#HeroCard {
    background: #ffffff;
    border: 1px solid #e0ded7;
    border-radius: 8px;
}

QFrame#AccentStrip {
    background: #0f766e;
    border-radius: 4px;
}

QFrame#Stepper {
    background: #ffffff;
    border: 1px solid #e0ded7;
    border-radius: 8px;
}

QLabel#AppBrand {
    color: #f8fafc;
    font-size: 20px;
    font-weight: 750;
}

QLabel#PageTitle {
    color: #17202a;
    font-size: 28px;
    font-weight: 760;
}

QLabel#TitleLabel {
    color: #17202a;
    font-size: 24px;
    font-weight: 760;
}

QLabel#SectionTitle {
    color: #18202a;
    font-size: 16px;
    font-weight: 720;
}

QLabel#SectionLabel {
    color: #18202a;
    font-size: 15px;
    font-weight: 720;
}

QLabel#MutedLabel {
    color: #607080;
}

QLabel#SmallMutedLabel {
    color: #9db0bc;
}

QLabel#SmallMutedLabel {
    font-size: 12px;
}

QLabel#VersionLabel {
    color: #8fa5af;
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
    background: #f7f6f2;
    color: #526170;
    border: 1px solid #e0ded7;
    border-radius: 7px;
    padding: 9px 12px;
    font-weight: 700;
    min-height: 22px;
    text-align: left;
}

QLabel#WizardStepPill[complete="true"], QPushButton#WizardStepPill[complete="true"] {
    background: #edf8f4;
    color: #0f766e;
    border: 1px solid #b7ded5;
}

QLabel#WizardStepPill[active="true"], QPushButton#WizardStepPill[active="true"] {
    background: #102027;
    color: #ffffff;
    border: 1px solid #102027;
}

QPushButton#WizardStepPill:disabled {
    background: #f7f6f2;
    color: #9aa6b2;
    border: 1px solid #e0ded7;
}

QLabel#StepNumber {
    color: #b56a19;
    font-size: 13px;
    font-weight: 800;
    letter-spacing: 0px;
}

QLabel#WizardStatus {
    background: #f8fafc;
    color: #334155;
    border-left: 4px solid #d09a45;
    border-radius: 7px;
    padding: 10px 12px;
    font-weight: 600;
}

QLabel#StatusPill {
    background: #edf8f4;
    color: #0f766e;
    border: 1px solid #b7ded5;
    border-radius: 8px;
    padding: 6px 10px;
    font-weight: 650;
}

QLabel#WarningPill {
    background: #fff5e5;
    color: #9a5718;
    border: 1px solid #f1cf9d;
    border-radius: 8px;
    padding: 6px 10px;
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
    color: #607080;
    font-size: 12px;
    padding: 0 4px;
}

QPushButton {
    background: #0f766e;
    color: #ffffff;
    border: none;
    border-radius: 7px;
    padding: 10px 14px;
    font-weight: 700;
    min-height: 24px;
}

QPushButton:hover {
    background: #0d9488;
}

QPushButton:disabled {
    background: #cbd5e1;
    color: #f8fafc;
}

QPushButton[secondary="true"] {
    background: #f2f4f5;
    color: #20303b;
    border: 1px solid #d8d5cc;
}

QPushButton[secondary="true"]:hover {
    background: #e9ecee;
}

QPushButton[nav="true"] {
    background: transparent;
    color: #c9d6dd;
    border: 1px solid transparent;
    text-align: left;
    padding: 10px 12px;
}

QPushButton[nav="true"][active="true"] {
    background: #18313a;
    color: #ffffff;
    border: 1px solid #315160;
}

QPushButton[quiet="true"] {
    background: transparent;
    color: #0f766e;
    border: 1px solid #b8e4dc;
}

QPushButton[tab="true"] {
    background: #ffffff;
    color: #435261;
    border: 1px solid #ddd7cc;
    padding: 9px 14px;
}

QPushButton[tab="true"][active="true"] {
    background: #102027;
    color: #ffffff;
    border: 1px solid #102027;
}

QLineEdit, QComboBox {
    background: #ffffff;
    border: 1px solid #d8d5cc;
    border-radius: 7px;
    padding: 9px 10px;
    min-height: 22px;
    selection-background-color: #b8e4dc;
}

QLineEdit:focus, QComboBox:focus {
    border: 1px solid #0f766e;
}

QComboBox#SidebarProjectCombo {
    background: #edf8f4;
    color: #0f766e;
    border: 1px solid #b7ded5;
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
    border: 1px solid #b7ded5;
    border-radius: 8px;
    padding: 6px 9px;
    min-height: 22px;
    font-size: 12px;
    font-weight: 650;
}

QListWidget, QPlainTextEdit, QTableWidget {
    background: #ffffff;
    border: 1px solid #ded8cd;
    border-radius: 8px;
    padding: 6px;
}

QTableWidget#ExcelMappingTable {
    background: #ffffff;
    alternate-background-color: #fbfaf7;
    border: 1px solid #ded8cd;
    border-radius: 8px;
    gridline-color: #eee8de;
    selection-background-color: #edf8f4;
    selection-color: #18202a;
}

QTableWidget#ExcelMappingTable QComboBox {
    padding: 7px 9px;
    min-height: 22px;
}

QListWidget#WizardQueueList {
    background: #fbfaf7;
    border: 1px solid #e0ded7;
    border-radius: 8px;
    padding: 8px;
}

QListWidget#DataEntryRecordList {
    background: #ffffff;
    border: 1px solid #ded8cd;
    border-radius: 8px;
    padding: 8px;
    min-width: 260px;
}

QListWidget#DataEntryRecordList::item {
    padding: 8px 10px;
    border-radius: 6px;
}

QListWidget#DataEntryRecordList::item:selected {
    background: #edf8f4;
    color: #0f766e;
}

QWidget#DataEntryForm {
    background: transparent;
}

QFrame#DataEntryFormShell {
    background: transparent;
}

QScrollArea#DataEntrySectionScroll {
    background: transparent;
    border: none;
}

QListWidget#DataEntryFormNav {
    background: #ffffff;
    border: 1px solid #e0ded7;
    border-radius: 8px;
    padding: 8px;
}

QListWidget#DataEntryFormNav::item {
    color: #334155;
    padding: 9px 11px;
    border-radius: 7px;
    font-weight: 650;
}

QListWidget#DataEntryFormNav::item:selected {
    background: #102027;
    color: #ffffff;
}

QListWidget#DataEntryFormNav::item:hover {
    background: #edf8f4;
    color: #0f766e;
}

QStackedWidget#DataEntryFormStack {
    background: transparent;
}

QLabel#DataEntryRecordTitle {
    color: #17202a;
    font-size: 22px;
    font-weight: 760;
}

QFrame#DataEntryFormSection {
    background: #ffffff;
    border: 1px solid #e0ded7;
    border-radius: 8px;
}

QFrame#DataEntryFieldRow {
    background: #fbfaf7;
    border: 1px solid #ece7df;
    border-left: 4px solid #d8d5cc;
    border-radius: 8px;
    padding: 9px 10px;
}

QFrame#DataEntryFieldRow[field_state="filled"] {
    background: #f1fbf7;
    border: 1px solid #c9e9df;
    border-left: 4px solid #0f766e;
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
    color: #0f766e;
    border: 1px solid #b7ded5;
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

QFrame#DataEntryChoiceGroup {
    background: transparent;
}

QHeaderView::section {
    background: #ebe7df;
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
    background: #0f766e;
    border-radius: 6px;
}
"""
