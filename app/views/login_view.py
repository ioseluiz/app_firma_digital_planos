from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from app.models.vault_model import MIN_PASSWORD_LEN
from app.views.icons import icon
from app.views.styles import THEMES, TOKENS


def _label(text, role=None, wrap=False):
    lbl = QLabel(text)
    if role:
        lbl.setProperty("role", role)
    lbl.setWordWrap(wrap)
    return lbl


class _VaultDialog(QDialog):
    def __init__(self, title, theme="light", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{title} - DigitalSealer")
        self.setStyleSheet(THEMES[theme])
        self.setMinimumWidth(400)
        t = TOKENS[theme]

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(14)

        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icon("seal", t["accent"], 36).pixmap(36, 36))
        head.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(_label("DigitalSealer", "title"))
        titles.addWidget(_label(title, "muted"))
        head.addLayout(titles)
        head.addStretch()
        outer.addLayout(head)

        self.card = QFrame()
        self.card.setProperty("card", True)
        self.form = QVBoxLayout(self.card)
        self.form.setContentsMargins(18, 18, 18, 18)
        self.form.setSpacing(8)
        outer.addWidget(self.card)

        self.lbl_error = _label("", "danger", wrap=True)
        self.lbl_error.setVisible(False)
        outer.addWidget(self.lbl_error)

        self.btn_ok = QPushButton()
        self.btn_ok.setProperty("variant", "primary")
        self.btn_ok.setDefault(True)
        self.btn_ok.setMinimumHeight(36)
        outer.addWidget(self.btn_ok)

    def _password_field(self, placeholder):
        field = QLineEdit()
        field.setEchoMode(QLineEdit.EchoMode.Password)
        field.setPlaceholderText(placeholder)
        field.setMinimumHeight(34)
        return field

    def show_error(self, msg):
        self.lbl_error.setText(msg)
        self.lbl_error.setVisible(True)


class SetupDialog(_VaultDialog):
    """Primer arranque: nombre del profesional y contraseña maestra."""

    def __init__(self, theme="light", parent=None):
        super().__init__("Configuración inicial", theme, parent)
        self.form.addWidget(_label(
            "Crea una contraseña maestra. Protege tu sello y firma: se guardan cifrados en "
            "este equipo y solo se pueden usar con esta contraseña.", "muted", wrap=True))
        self.form.addSpacing(6)
        self.form.addWidget(_label("Nombre (aparece en los metadatos del PDF)", "section"))
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Ej.: Ing. José Luis Muñoz Mata")
        self.txt_name.setMinimumHeight(34)
        self.form.addWidget(self.txt_name)
        self.form.addSpacing(4)
        self.form.addWidget(_label("Contraseña maestra", "section"))
        self.txt_pass = self._password_field(f"Mínimo {MIN_PASSWORD_LEN} caracteres")
        self.txt_pass2 = self._password_field("Repite la contraseña")
        self.form.addWidget(self.txt_pass)
        self.form.addWidget(self.txt_pass2)
        self.form.addWidget(_label(
            "Importante: si olvidas esta contraseña no hay forma de recuperar el sello guardado; "
            "tendrías que volver a configurarlo.", "warning", wrap=True))
        self.btn_ok.setText("Crear y continuar")
        self.btn_ok.clicked.connect(self._validate)

    def _validate(self):
        p1, p2 = self.txt_pass.text(), self.txt_pass2.text()
        if not self.txt_name.text().strip():
            self.show_error("Escribe tu nombre.")
        elif len(p1) < MIN_PASSWORD_LEN:
            self.show_error(f"La contraseña debe tener al menos {MIN_PASSWORD_LEN} caracteres.")
        elif p1 != p2:
            self.show_error("Las contraseñas no coinciden.")
        else:
            self.accept()

    def values(self):
        return self.txt_name.text().strip(), self.txt_pass.text()


class UnlockDialog(_VaultDialog):
    """Desbloqueo con la contraseña maestra (al iniciar o tras inactividad)."""

    def __init__(self, theme="light", reason="", parent=None):
        super().__init__("Desbloquear", theme, parent)
        if reason:
            self.form.addWidget(_label(reason, "muted", wrap=True))
        self.form.addWidget(_label("Contraseña maestra", "section"))
        self.txt_pass = self._password_field("Contraseña")
        self.form.addWidget(self.txt_pass)
        self.btn_ok.setText("Desbloquear")
        self.txt_pass.setFocus(Qt.FocusReason.OtherFocusReason)

    def password(self):
        return self.txt_pass.text()

    def clear(self):
        self.txt_pass.clear()
        self.txt_pass.setFocus()
