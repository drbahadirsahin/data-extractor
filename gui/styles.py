APP_STYLE = """
QWidget {
    background: #f6f4ef;
    color: #17202a;
    font-family: "Avenir Next", "Aptos", "Segoe UI", sans-serif;
    font-size: 14px;
}

QMainWindow {
    background: #f6f4ef;
}

QFrame#HeroCard, QFrame#PanelCard {
    background: #fffdf9;
    border: 1px solid #e3ded5;
    border-radius: 8px;
}

QLabel#TitleLabel {
    font-size: 28px;
    font-weight: 780;
    color: #111827;
}

QLabel#SectionLabel {
    font-size: 17px;
    font-weight: 760;
    color: #17202a;
}

QLabel#MutedLabel {
    color: #667789;
}

QPushButton {
    background: #0b7a71;
    color: white;
    border: none;
    border-radius: 7px;
    padding: 10px 15px;
    font-weight: 700;
}

QPushButton:hover {
    background: #0f8f84;
}

QPushButton[secondary="true"] {
    background: #f7f6f2;
    color: #23323f;
    border: 1px solid #ded8cd;
}

QLineEdit, QComboBox {
    background: #ffffff;
    border: 1px solid #ddd8cf;
    border-radius: 7px;
    padding: 9px 11px;
}

QListWidget, QPlainTextEdit, QTableWidget {
    background: #ffffff;
    border: 1px solid #ded8cd;
    border-radius: 8px;
    padding: 6px;
    selection-background-color: #e8f6f2;
    selection-color: #17202a;
}

QTableWidget {
    gridline-color: #f0ebe4;
}

QHeaderView::section {
    background: #ede8df;
    color: #334155;
    border: none;
    border-bottom: 1px solid #ded8cd;
    padding: 8px;
    font-weight: 700;
}

QPlainTextEdit {
    selection-background-color: #b9e4dc;
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
    width: 8px;
}
"""
