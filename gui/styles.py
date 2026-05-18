APP_STYLE = """
QWidget {
    background: #f5f0e8;
    color: #1f1b16;
    font-family: "Avenir Next", "Segoe UI", sans-serif;
    font-size: 14px;
}

QMainWindow {
    background: #efe7db;
}

QFrame#HeroCard, QFrame#PanelCard {
    background: #fffaf3;
    border: 1px solid #d7c8b6;
    border-radius: 20px;
}

QLabel#TitleLabel {
    font-size: 28px;
    font-weight: 700;
    color: #241b12;
}

QLabel#SectionLabel {
    font-size: 17px;
    font-weight: 700;
    color: #4e3422;
}

QLabel#MutedLabel {
    color: #65564a;
}

QPushButton {
    background: #1f6f5f;
    color: white;
    border: none;
    border-radius: 12px;
    padding: 10px 16px;
    font-weight: 700;
}

QPushButton:hover {
    background: #18594d;
}

QPushButton[secondary="true"] {
    background: #e6d9c8;
    color: #2b241d;
}

QLineEdit, QComboBox {
    background: #fffdf9;
    border: 1px solid #ccbba8;
    border-radius: 10px;
    padding: 8px 10px;
}

QListWidget, QPlainTextEdit, QTableWidget {
    background: #fffdf9;
    border: 1px solid #ccbba8;
    border-radius: 12px;
    padding: 6px;
}

QTableWidget {
    gridline-color: #e7d8c8;
}

QHeaderView::section {
    background: #f2e7d8;
    color: #4e3422;
    border: none;
    border-bottom: 1px solid #d7c8b6;
    padding: 8px;
    font-weight: 700;
}

QPlainTextEdit {
    selection-background-color: #c9e4dc;
}

QProgressBar {
    background: #efe4d6;
    border: 1px solid #d7c8b6;
    border-radius: 10px;
    text-align: center;
    min-height: 16px;
}

QProgressBar::chunk {
    background: #1f6f5f;
    border-radius: 8px;
}

QSplitter::handle {
    background: #e7d8c8;
    width: 8px;
}
"""
