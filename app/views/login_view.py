from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
)
from PyQt6.QtCore import Qt
from app.views.styles import THEMES  # <--- CAMBIO 1: Importar THEMES


class LoginView(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Acceso - DigitalSealer")
        self.setFixedSize(300, 250)
        self.setStyleSheet(
            THEMES["dark"]
        )  # <--- CAMBIO 2: Usar el tema dark por defecto

        layout = QVBoxLayout()

        self.lbl_title = QLabel("Iniciar Sesión")
        self.lbl_title.setObjectName("Header")
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.txt_user = QLineEdit()
        self.txt_user.setPlaceholderText("Usuario")

        self.txt_pass = QLineEdit()
        self.txt_pass.setPlaceholderText("Contraseña")
        self.txt_pass.setEchoMode(QLineEdit.EchoMode.Password)

        self.btn_login = QPushButton("Entrar")

        layout.addWidget(self.lbl_title)
        layout.addSpacing(20)
        layout.addWidget(self.txt_user)
        layout.addWidget(self.txt_pass)
        layout.addWidget(self.btn_login)

        self.setLayout(layout)

    def get_credentials(self):
        return self.txt_user.text(), self.txt_pass.text()

    def show_error(self, msg):
        QMessageBox.critical(self, "Error", msg)
