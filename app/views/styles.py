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
    border: 1px solid #cccccc;
    border-radius: 4px;
    padding: 5px;
    color: #333;
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
    background-color: #008ae6;
}}

QPushButton:pressed {{
    background-color: #005c99;
}}

QPushButton:disabled {{
    background-color: #e0e0e0;
    color: #999;
}}

QListWidget, QTableWidget {{
    background-color: #ffffff;
    border: 1px solid #cccccc;
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
    border: 1px solid #ccc;
}}

QLabel#Header {{
    font-size: 18px;
    font-weight: bold;
    color: #005c99;
}}
"""

THEMES = {"dark": DARK_THEME, "light": LIGHT_THEME}
