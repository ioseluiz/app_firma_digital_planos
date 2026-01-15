# app/views/styles.py

# Simplificamos las fuentes para compatibilidad universal (Mac/Windows)
FONTS = "font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;"

DARK_THEME = f"""
QWidget {{
    background-color: #2b2b2b;
    color: #ffffff;
    {FONTS}
    font-size: 14px;
}}

QLineEdit {{
    background-color: #3c3f41;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 5px;
    color: #fff;
    selection-background-color: #007acc;
}}

QPushButton {{
    background-color: #007acc;
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    font-weight: bold;
}}

QPushButton:hover {{
    background-color: #0098ff;
}}

QPushButton:pressed {{
    background-color: #005c99;
}}

QPushButton:disabled {{
    background-color: #555;
    color: #aaa;
}}

QListWidget, QTableWidget {{
    background-color: #3c3f41;
    border: 1px solid #555;
    border-radius: 4px;
    color: #fff;
}}

QListWidget::item:selected, QTableWidget::item:selected {{
    background-color: #007acc;
    color: white;
}}

QHeaderView::section {{
    background-color: #3c3f41;
    color: white;
    padding: 4px;
    border: 1px solid #555;
}}

/* --- ESTILO PESTAÑAS (DARK) --- */
QTabWidget::pane {{
    border: 1px solid #555;
    background: #2b2b2b;
}}
QTabBar::tab {{
    background: #3c3f41;
    border: 1px solid #555;
    padding: 6px 12px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}}
QTabBar::tab:selected {{
    background: #007acc;
    color: white;
    border-bottom-color: #007acc;
}}
QTabBar::tab:!selected {{
    color: #aaa;
}}

QLabel#Header {{
    font-size: 18px;
    font-weight: bold;
    color: #00aaff;
}}
"""

LIGHT_THEME = f"""
QWidget {{
    background-color: #f5f5f5;
    color: #333333;
    {FONTS}
    font-size: 14px;
}}

QLineEdit {{
    background-color: #ffffff;
    border: 1px solid #aaaaaa; /* Borde más visible */
    border-radius: 4px;
    padding: 5px;
    color: #333;
    selection-background-color: #007acc;
}}

QPushButton {{
    background-color: #007acc;
    color: white;
    border: 1px solid #005c99;
    padding: 8px 16px;
    border-radius: 4px;
    font-weight: bold;
}}

QPushButton:hover {{
    background-color: #008ae6;
}}

QPushButton:pressed {{
    background-color: #005c99;
}}

QPushButton:disabled {{
    background-color: #e0e0e0;
    color: #999;
    border: 1px solid #ccc;
}}

QListWidget, QTableWidget {{
    background-color: #ffffff;
    border: 1px solid #aaaaaa; /* Borde más oscuro */
    border-radius: 4px;
    color: #333;
}}

QListWidget::item:selected, QTableWidget::item:selected {{
    background-color: #007acc;
    color: white;
}}

QHeaderView::section {{
    background-color: #e0e0e0;
    color: #333;
    padding: 4px;
    border: 1px solid #999;
}}

/* --- ESTILO PESTAÑAS (LIGHT) - CORREGIDO --- */
QTabWidget::pane {{
    border: 1px solid #999999; /* Marco gris oscuro alrededor del contenido */
    background: #f5f5f5;
    top: -1px; 
}}

QTabBar::tab {{
    background: #e0e0e0; /* Fondo gris para pestañas inactivas */
    border: 1px solid #999999;
    padding: 6px 12px;
    margin-right: 2px;
    border-bottom-color: #999999;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    color: #555;
}}

QTabBar::tab:selected {{
    background: #ffffff; /* Fondo blanco para la activa */
    color: #000;
    border-bottom-color: #f5f5f5; /* "Borra" la línea inferior para fusionar con el panel */
    font-weight: bold;
}}

QTabBar::tab:hover {{
    background: #dcdcdc;
}}

QLabel#Header {{
    font-size: 18px;
    font-weight: bold;
    color: #005c99;
}}
"""

THEMES = {"dark": DARK_THEME, "light": LIGHT_THEME}