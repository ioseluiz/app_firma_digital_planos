"""Verificar si un PDF fue emitido por esta instalación (hash / ID de sellado en el registro)."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QFileDialog, QFrame, QLabel, QPushButton, QVBoxLayout

from app.views.styles import THEMES


class VerifyDialog(QDialog):
    def __init__(self, verify_fn, theme="light", parent=None):
        """verify_fn(path) -> (estado, titulo, detalle) con estado en {'ok','modified','unknown','error'}."""
        super().__init__(parent)
        self._verify = verify_fn
        self.setWindowTitle("Verificar documento")
        self.setStyleSheet(THEMES[theme])
        self.setMinimumWidth(520)
        self.setAcceptDrops(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)
        title = QLabel("Verificar documento")
        title.setProperty("role", "title")
        lay.addWidget(title)
        hint = QLabel("Arrastra aquí un PDF (o elígelo) para comprobar si lo emitiste tú con esta aplicación "
                      "y si no ha sido modificado desde entonces.")
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.drop = QFrame()
        self.drop.setProperty("card", True)
        self.drop.setMinimumHeight(150)
        d = QVBoxLayout(self.drop)
        self.lbl_status = QLabel("Suelta un PDF aquí")
        self.lbl_status.setProperty("role", "heading")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_detail = QLabel("")
        self.lbl_detail.setWordWrap(True)
        self.lbl_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        d.addWidget(self.lbl_status)
        d.addWidget(self.lbl_detail)
        lay.addWidget(self.drop)

        btn = QPushButton("Elegir PDF…")
        btn.clicked.connect(self._choose)
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "PDF a verificar", "", "PDF (*.pdf)")
        if path:
            self.check(path)

    def check(self, path):
        state, title, detail = self._verify(path)
        role = {"ok": "success", "modified": "warning", "unknown": "danger", "error": "danger"}[state]
        self.lbl_status.setText(title)
        self.lbl_status.setProperty("role", role)
        self.lbl_status.style().unpolish(self.lbl_status)
        self.lbl_status.style().polish(self.lbl_status)
        self.lbl_detail.setText(detail)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            self.check(urls[0].toLocalFile())
