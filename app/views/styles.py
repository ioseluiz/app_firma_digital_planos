# app/views/styles.py
"""Tema visual: tokens de color claro/oscuro y hoja de estilos generada a partir de ellos."""

TOKENS = {
    "light": {
        "bg": "#f3f4f6",
        "surface": "#ffffff",
        "surface_alt": "#eef0f3",
        "border": "#d8dce2",
        "border_strong": "#b9c0ca",
        "text": "#1c222b",
        "text_muted": "#5e6977",
        "accent": "#1f6feb",
        "accent_hover": "#195fcf",
        "accent_text": "#ffffff",
        "accent_soft": "#dbe8fd",
        "danger": "#cf222e",
        "success": "#1a7f37",
        "warning": "#9a6700",
        "canvas": "#dfe3e8",
        "page_shadow": "#26000000",
    },
    "dark": {
        "bg": "#15181c",
        "surface": "#1d2127",
        "surface_alt": "#252a31",
        "border": "#333a44",
        "border_strong": "#4a5361",
        "text": "#e6e9ee",
        "text_muted": "#97a1af",
        "accent": "#4c8dff",
        "accent_hover": "#6aa0ff",
        "accent_text": "#0b1220",
        "accent_soft": "#1f3050",
        "danger": "#f0565f",
        "success": "#3fb950",
        "warning": "#d29922",
        "canvas": "#0e1013",
        "page_shadow": "#88000000",
    },
}

FONT_FAMILY = "'Segoe UI', 'Helvetica Neue', Arial, sans-serif"


def build_qss(t):
    return f"""
QWidget {{
    background-color: {t['bg']};
    color: {t['text']};
    font-family: {FONT_FAMILY};
    font-size: 13px;
}}
QMainWindow::separator {{ background: {t['border']}; width: 1px; height: 1px; }}
QSplitter::handle {{ background: {t['border']}; }}
QSplitter::handle:horizontal {{ width: 1px; }}

QToolTip {{
    background-color: {t['surface']}; color: {t['text']};
    border: 1px solid {t['border_strong']}; padding: 4px 6px;
}}

/* --- Tarjetas y etiquetas --- */
QFrame[card="true"] {{
    background-color: {t['surface']};
    border: 1px solid {t['border']};
    border-radius: 8px;
}}
QFrame[card="true"] QLabel, QFrame[card="true"] QCheckBox {{ background: transparent; }}
QLabel[role="heading"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="section"] {{
    font-size: 11px; font-weight: 600; color: {t['text_muted']};
}}
QLabel[role="muted"] {{ color: {t['text_muted']}; font-size: 12px; }}
QLabel[role="danger"] {{ color: {t['danger']}; }}
QLabel[role="success"] {{ color: {t['success']}; }}
QLabel[role="warning"] {{ color: {t['warning']}; }}
QLabel[role="title"] {{ font-size: 20px; font-weight: 600; }}

/* --- Botones --- */
QPushButton, QToolButton {{
    background-color: {t['surface']};
    color: {t['text']};
    border: 1px solid {t['border_strong']};
    border-radius: 6px;
    padding: 6px 12px;
}}
QPushButton:hover, QToolButton:hover {{ background-color: {t['surface_alt']}; }}
QPushButton:pressed, QToolButton:pressed {{ background-color: {t['border']}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {t['text_muted']}; border-color: {t['border']}; }}
QPushButton:checked, QToolButton:checked {{ background-color: {t['accent_soft']}; border-color: {t['accent']}; }}
QPushButton[variant="primary"] {{
    background-color: {t['accent']}; color: {t['accent_text']};
    border: 1px solid {t['accent']}; font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{ background-color: {t['accent_hover']}; }}
QPushButton[variant="primary"]:disabled {{
    background-color: {t['surface_alt']}; color: {t['text_muted']}; border-color: {t['border']};
}}
QPushButton[variant="danger"] {{ color: {t['danger']}; }}
QPushButton[variant="link"] {{ border: none; background: transparent; color: {t['accent']}; padding: 2px; }}

QToolBar {{
    background-color: {t['surface']};
    border: none; border-bottom: 1px solid {t['border']};
    spacing: 4px; padding: 6px 8px;
}}
QToolBar QToolButton {{ border: 1px solid transparent; background: transparent; padding: 5px 8px; }}
QToolBar QToolButton:hover {{ background-color: {t['surface_alt']}; border-color: {t['border']}; }}
QToolBar::separator {{ background: {t['border']}; width: 1px; margin: 4px 6px; }}
QToolBar QLabel, QWidget#spacer {{ background: transparent; }}

/* --- Entradas --- */
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {{
    background-color: {t['surface']};
    border: 1px solid {t['border_strong']};
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: {t['accent']};
    selection-color: {t['accent_text']};
}}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {t['accent']}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background-color: {t['surface']}; border: 1px solid {t['border_strong']};
    selection-background-color: {t['accent_soft']}; selection-color: {t['text']};
}}
QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{
    width: 15px; height: 15px; border-radius: 4px;
    border: 1px solid {t['border_strong']}; background: {t['surface']};
}}
QCheckBox::indicator:hover {{ border-color: {t['accent']}; }}
QCheckBox::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']}; }}

/* --- Listas / árbol --- */
QTreeWidget, QListWidget, QTableWidget {{
    background-color: {t['surface']};
    border: none;
    outline: none;
}}
QTreeWidget::item {{ padding: 4px 2px; border-radius: 4px; }}
QTreeWidget::item:hover {{ background-color: {t['surface_alt']}; }}
QTreeWidget::item:selected {{ background-color: {t['accent_soft']}; color: {t['text']}; }}
QHeaderView::section {{
    background-color: {t['surface_alt']}; color: {t['text_muted']};
    border: none; border-bottom: 1px solid {t['border']}; padding: 4px;
}}

QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle {{ background: {t['border_strong']}; border-radius: 4px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {t['text_muted']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QGraphicsView {{ background-color: {t['canvas']}; border: none; }}

/* --- Barra de estado y progreso --- */
QStatusBar {{ background-color: {t['surface']}; border-top: 1px solid {t['border']}; color: {t['text_muted']}; }}
QStatusBar QLabel {{ background: transparent; color: {t['text_muted']}; padding: 0 6px; }}
QProgressBar {{
    background-color: {t['surface_alt']}; border: 1px solid {t['border']};
    border-radius: 5px; text-align: center; height: 14px; color: {t['text']};
}}
QProgressBar::chunk {{ background-color: {t['accent']}; border-radius: 4px; }}

QMenu {{ background-color: {t['surface']}; border: 1px solid {t['border_strong']}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background-color: {t['accent_soft']}; color: {t['text']}; }}
QMenu::item:disabled {{ color: {t['text_muted']}; }}
QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 6px; }}

QDialog {{ background-color: {t['bg']}; }}
QMessageBox {{ background-color: {t['surface']}; }}
"""


THEMES = {name: build_qss(tokens) for name, tokens in TOKENS.items()}
