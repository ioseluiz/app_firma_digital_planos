"""Ventana principal: navegador de hojas | lienzo de la hoja | propiedades."""
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QLabel, QMainWindow, QProgressBar, QPushButton, QSizePolicy, QSplitter, QToolBar, QVBoxLayout,
    QWidget,
)

from app import __version__
from app.utils import geometry
from app.views.icons import icon
from app.views.page_canvas import PageCanvas
from app.views.page_navigator import PageNavigator
from app.views.properties_panel import PropertiesPanel
from app.views.styles import THEMES, TOKENS


class MainView(QMainWindow):
    closing = pyqtSignal()

    def __init__(self, owner_name, theme="light"):
        super().__init__()
        self.setWindowTitle(f"DigitalSealer {__version__} · {owner_name}")
        self.resize(1440, 900)
        self.setMinimumSize(1000, 640)
        self.theme = theme
        t = TOKENS[theme]

        # --- Barra de herramientas -----------------------------------------
        tb = QToolBar("Principal")
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(tb)
        self.toolbar = tb

        self.act_open = QAction("Abrir PDFs", self)
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open.setToolTip("Abrir planos o reportes PDF (también puedes arrastrarlos) · Ctrl+O")
        self.act_clear = QAction("Limpiar", self)
        self.act_clear.setToolTip("Quitar todos los archivos de la lista")
        self.act_stamp = QAction("Mi sello", self)
        self.act_verify = QAction("Verificar", self)
        self.act_verify.setToolTip("Comprobar si un PDF fue emitido por ti y no fue modificado")
        self.act_undo = QAction("Deshacer", self)
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.act_redo = QAction("Rehacer", self)
        self.act_redo.setShortcuts([QKeySequence.StandardKey.Redo, QKeySequence("Ctrl+Y")])
        self.act_zoom_out = QAction("", self)
        self.act_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self.act_zoom_out.setToolTip("Alejar (Ctrl+-)")
        self.act_zoom_in = QAction("", self)
        self.act_zoom_in.setShortcuts([QKeySequence.StandardKey.ZoomIn, QKeySequence("Ctrl+=")])
        self.act_zoom_in.setToolTip("Acercar (Ctrl++)")
        self.act_fit = QAction("Ajustar", self)
        self.act_fit.setShortcut(QKeySequence("Ctrl+0"))
        self.act_fit.setToolTip("Ver la hoja completa (Ctrl+0)")
        self.act_prev = QAction("Hoja anterior", self)
        self.act_prev.setShortcut(QKeySequence(Qt.Key.Key_PageUp))
        self.act_next = QAction("Hoja siguiente", self)
        self.act_next.setShortcut(QKeySequence(Qt.Key.Key_PageDown))
        self.act_theme = QAction("", self)
        self.act_theme.setToolTip("Cambiar tema claro/oscuro")
        self.act_lock = QAction("Bloquear", self)
        self.act_lock.setShortcut(QKeySequence("Ctrl+L"))
        self.act_lock.setToolTip("Bloquear la aplicación (Ctrl+L)")
        self.addActions([self.act_prev, self.act_next])

        tb.addAction(self.act_open)
        tb.addAction(self.act_clear)
        tb.addSeparator()
        tb.addAction(self.act_stamp)
        tb.addAction(self.act_verify)
        tb.addSeparator()
        tb.addAction(self.act_undo)
        tb.addAction(self.act_redo)
        tb.addSeparator()
        tb.addAction(self.act_zoom_out)
        self.lbl_zoom = QLabel("100 %")
        self.lbl_zoom.setMinimumWidth(52)
        self.lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tb.addWidget(self.lbl_zoom)
        tb.addAction(self.act_zoom_in)
        tb.addAction(self.act_fit)
        spacer = QWidget()
        spacer.setObjectName("spacer")
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        tb.addAction(self.act_theme)
        tb.addAction(self.act_lock)
        self.btn_seal = QPushButton("Sellar")
        self.btn_seal.setProperty("variant", "primary")
        self.btn_seal.setMinimumHeight(34)
        self.btn_seal.setMinimumWidth(170)
        tb.addWidget(self.btn_seal)

        # --- Paneles --------------------------------------------------------
        self.navigator = PageNavigator(t)
        self.canvas = PageCanvas(t)
        self.properties = PropertiesPanel(t)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)
        hdr = QLabel("  ARCHIVOS Y HOJAS")
        hdr.setProperty("role", "section")
        hdr.setMinimumHeight(30)
        ll.addWidget(hdr)
        ll.addWidget(self.navigator)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(left)
        split.addWidget(self.canvas)
        split.addWidget(self.properties)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setStretchFactor(2, 0)
        split.setSizes([280, 820, 340])
        split.setChildrenCollapsible(False)
        left.setMinimumWidth(220)
        self.properties.setMinimumWidth(320)
        self.setCentralWidget(split)

        # --- Barra de estado -------------------------------------------------
        sb = self.statusBar()
        self.lbl_status = QLabel("Listo")
        self.lbl_cursor = QLabel("")
        self.lbl_cursor.setMinimumWidth(170)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setVisible(False)
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setVisible(False)
        sb.addWidget(self.lbl_status, 1)
        sb.addPermanentWidget(self.progress)
        sb.addPermanentWidget(self.btn_cancel)
        sb.addPermanentWidget(self.lbl_cursor)

        self.canvas.zoom_changed.connect(lambda z: self.lbl_zoom.setText(f"{z * 100:.0f} %"))
        self.canvas.cursor_moved.connect(self._show_cursor)
        self.set_theme(theme)

    # ------------------------------------------------------------ helpers
    def set_theme(self, theme):
        self.theme = theme
        t = TOKENS[theme]
        self.setStyleSheet(THEMES[theme])
        c = t["text"]
        self.act_open.setIcon(icon("open", c))
        self.act_clear.setIcon(icon("clear", c))
        self.act_stamp.setIcon(icon("stamp", c))
        self.act_verify.setIcon(icon("verify", c))
        self.act_undo.setIcon(icon("undo", c))
        self.act_redo.setIcon(icon("redo", c))
        self.act_zoom_in.setIcon(icon("zoom_in", c))
        self.act_zoom_out.setIcon(icon("zoom_out", c))
        self.act_fit.setIcon(icon("fit", c))
        self.act_lock.setIcon(icon("lock", c))
        self.act_theme.setIcon(icon("sun" if theme == "dark" else "moon", c))
        self.btn_seal.setIcon(icon("seal", t["accent_text"]))
        self.navigator.set_tokens(t)
        self.canvas.set_tokens(t)
        self.properties.set_tokens(t)

    def set_seal_count(self, pages, files):
        if pages:
            self.btn_seal.setText(f"Sellar {pages} hoja{'s' if pages != 1 else ''}")
            self.btn_seal.setToolTip(f"{pages} hojas en {files} archivo{'s' if files != 1 else ''}")
        else:
            self.btn_seal.setText("Sellar")
            self.btn_seal.setToolTip("No hay hojas con sello")
        self.btn_seal.setEnabled(pages > 0)

    def set_busy(self, busy, cancellable=False):
        self.progress.setVisible(busy)
        self.btn_cancel.setVisible(busy and cancellable)
        if busy:
            self.progress.setValue(0)
        for w in (self.act_open, self.act_clear, self.act_stamp):
            w.setEnabled(not busy)
        if busy:
            self.btn_seal.setEnabled(False)

    def set_status(self, text):
        self.lbl_status.setText(text)

    def _show_cursor(self, pos):
        if pos is None:
            self.lbl_cursor.setText("")
        else:
            self.lbl_cursor.setText(f"X {geometry.pt_to_mm(pos[0]):7.1f} mm   Y {geometry.pt_to_mm(pos[1]):7.1f} mm")

    def closeEvent(self, event):
        self.closing.emit()
        super().closeEvent(event)
