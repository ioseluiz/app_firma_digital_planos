from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QListWidget,
    QLabel,
    QFileDialog,
    QMessageBox,
    QTabWidget,
    QLineEdit,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QInputDialog,
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt
from app.views.styles import THEMES
import os


class MainView(QMainWindow):
    def __init__(self, user_data):
        super().__init__()
        self.user_data = user_data
        self.setWindowTitle(f"DigitalSealer - Usuario: {user_data['username']}")
        self.resize(1000, 700)  # Un poco más grande para acomodar nuevos controles

        # Tema Inicial
        self.setStyleSheet(THEMES["dark"])

        # Widget Central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout(central_widget)

        # --- HEADER ---
        header_layout = QHBoxLayout()
        role_text = "Administrador" if user_data["role"] == "admin" else "Ingeniero"
        self.lbl_info = QLabel(f"Rol: {role_text}")

        # Botón cambio de tema
        self.btn_toggle_theme = QPushButton("☀️ / 🌙")
        self.btn_toggle_theme.setFixedWidth(60)
        self.btn_toggle_theme.setToolTip("Cambiar Tema")

        self.btn_logout = QPushButton("Cerrar Sesión")
        self.btn_logout.setStyleSheet("background-color: #d9534f;")

        header_layout.addWidget(self.lbl_info)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_toggle_theme)
        header_layout.addWidget(self.btn_logout)

        self.main_layout.addLayout(header_layout)

        # Tabs
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)

        # Tab 1: Firmar
        self.tab_signing = QWidget()
        self.setup_signing_tab()
        self.tabs.addTab(self.tab_signing, "Firmar Planos")

        # Tab 2: Configuración (Ingenieros)
        if user_data["role"] != "admin":
            self.tab_config = QWidget()
            self.setup_config_tab()
            self.tabs.addTab(self.tab_config, "Mi Firma Digital")

        # Tab 3: Admin (Administradores)
        if user_data["role"] == "admin":
            self.tab_admin = QWidget()
            self.setup_admin_tab()
            self.tabs.addTab(self.tab_admin, "Administración")

    def set_theme(self, theme_name):
        if theme_name in THEMES:
            self.setStyleSheet(THEMES[theme_name])

    def setup_signing_tab(self):
        layout = QHBoxLayout(self.tab_signing)

        # --- COLUMNA IZQUIERDA: Lista Archivos ---
        left_layout = QVBoxLayout()
        lbl_instr = QLabel("1. Arrastra archivos PDF aquí:")
        self.btn_add_files = QPushButton("Seleccionar PDFs")
        self.list_files = QListWidget()
        self.list_files.setAcceptDrops(True)
        self.list_files.setDragDropMode(QListWidget.DragDropMode.DropOnly)

        self.list_files.dragEnterEvent = self.dragEnterEvent
        self.list_files.dragMoveEvent = self.dragMoveEvent
        self.list_files.dropEvent = self.dropEvent

        left_layout.addWidget(lbl_instr)
        left_layout.addWidget(self.btn_add_files)
        left_layout.addWidget(self.list_files)

        # --- COLUMNA DERECHA: Configuración y Acciones ---
        right_layout = QVBoxLayout()

        # Estado de la firma
        self.lbl_signature_status = QLabel()
        self.lbl_signature_status.setWordWrap(True)

        # --- SECCION DE COORDENADAS (NUEVO) ---
        lbl_coords = QLabel("2. Posición de la Firma:")
        lbl_coords.setStyleSheet("font-weight: bold; margin-top: 10px;")

        self.lbl_coords_status = QLabel("Posición: Predeterminada (400, 700)")
        self.lbl_coords_status.setStyleSheet("color: #888; font-size: 12px;")

        self.btn_set_coords = QPushButton("📍 Definir visualmente")
        self.btn_set_coords.setToolTip(
            "Abre una previsualización del primer PDF para hacer clic donde va la firma"
        )
        self.btn_set_coords.setStyleSheet(
            "background-color: #f0ad4e; color: black;"
        )  # Color distintivo

        # --- SECCION CARPETA SALIDA ---
        lbl_dest = QLabel("3. Carpeta Destino:")
        lbl_dest.setStyleSheet("font-weight: bold; margin-top: 10px;")

        self.lbl_output_dir = QLabel("Destino: Carpeta original del archivo")
        self.lbl_output_dir.setWordWrap(True)
        self.lbl_output_dir.setStyleSheet(
            "color: #888; font-style: italic; font-size: 11px;"
        )

        self.btn_select_output = QPushButton("Cambiar Carpeta Destino")
        self.btn_select_output.setStyleSheet("background-color: #5bc0de; color: white;")

        # Botones de Acción Principal
        self.btn_process = QPushButton("4. Ejecutar Firmado")
        self.btn_process.setMinimumHeight(50)
        self.btn_clear = QPushButton("Limpiar Lista")

        right_layout.addWidget(self.lbl_signature_status)

        # Agregamos widgets Coordenadas
        right_layout.addWidget(lbl_coords)
        right_layout.addWidget(self.lbl_coords_status)
        right_layout.addWidget(self.btn_set_coords)

        # Agregamos widgets Carpeta
        right_layout.addWidget(lbl_dest)
        right_layout.addWidget(self.lbl_output_dir)
        right_layout.addWidget(self.btn_select_output)

        right_layout.addStretch()
        right_layout.addWidget(self.btn_process)
        right_layout.addWidget(self.btn_clear)

        layout.addLayout(left_layout, 60)
        layout.addLayout(right_layout, 40)

        self.update_signature_status_label()

    def setup_config_tab(self):
        layout = QVBoxLayout(self.tab_config)

        lbl_info = QLabel("Configuración de Firma Digital")
        lbl_info.setObjectName("Header")

        lbl_instr = QLabel("Tu firma actual:")

        # Area de Previsualización
        self.lbl_preview = QLabel()
        self.lbl_preview.setFixedSize(400, 200)
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setStyleSheet("""
            border: 2px dashed #555; 
            background-color: rgba(0,0,0,0.1);
            border-radius: 10px;
        """)
        self.lbl_preview.setText("Sin firma cargada")

        self.lbl_path_text = QLabel("Ruta: Ninguna")
        self.lbl_path_text.setStyleSheet("color: #888; font-size: 11px;")

        self.btn_upload_sig = QPushButton("Cargar / Cambiar Firma")
        self.btn_upload_sig.setFixedWidth(200)

        layout.addWidget(lbl_info)
        layout.addSpacing(10)
        layout.addWidget(lbl_instr)
        layout.addWidget(self.lbl_preview)
        layout.addWidget(self.lbl_path_text)
        layout.addSpacing(10)
        layout.addWidget(self.btn_upload_sig)
        layout.addStretch()

    def set_signature_image(self, path):
        """Muestra la imagen en el recuadro de previsualización"""
        if path and os.path.exists(path):
            pixmap = QPixmap(path)
            # Escalar manteniendo la relación de aspecto
            scaled_pixmap = pixmap.scaled(
                self.lbl_preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.lbl_preview.setPixmap(scaled_pixmap)
            self.lbl_path_text.setText(f"Ruta: {path}")

            # Actualizar estado visual de la pestaña principal
            self.lbl_signature_status.setText(
                "✅ Firma Digital Cargada\nLista para usar."
            )
            self.lbl_signature_status.setStyleSheet(
                "color: #00ff00; font-weight: bold;"
            )
            self.btn_process.setEnabled(True)
        else:
            self.lbl_preview.clear()
            self.lbl_preview.setText("❌ No se encontró el archivo de firma")
            self.lbl_path_text.setText("Ruta: No válida")

            self.lbl_signature_status.setText(
                "❌ Falta Configurar Firma.\nVe a la pestaña 'Mi Firma'."
            )
            self.lbl_signature_status.setStyleSheet(
                "color: #ff5555; font-weight: bold;"
            )
            self.btn_process.setEnabled(False)

    def setup_admin_tab(self):
        layout = QHBoxLayout(self.tab_admin)

        # Panel Izquierdo
        left_panel = QVBoxLayout()
        lbl_create = QLabel("Crear Nuevo Usuario")
        lbl_create.setObjectName("Header")

        self.txt_new_user = QLineEdit()
        self.txt_new_user.setPlaceholderText("Nombre de Usuario")

        self.txt_new_pass = QLineEdit()
        self.txt_new_pass.setPlaceholderText("Contraseña")
        self.txt_new_pass.setEchoMode(QLineEdit.EchoMode.Password)

        self.cmb_role = QComboBox()
        self.cmb_role.addItems(["ingeniero", "admin"])

        self.btn_create_user = QPushButton("Crear Usuario")

        left_panel.addWidget(lbl_create)
        left_panel.addWidget(self.txt_new_user)
        left_panel.addWidget(self.txt_new_pass)
        left_panel.addWidget(self.cmb_role)
        left_panel.addWidget(self.btn_create_user)
        left_panel.addStretch()

        # Panel Derecho
        right_panel = QVBoxLayout()
        lbl_list = QLabel("Usuarios Existentes")
        lbl_list.setObjectName("Header")

        self.table_users = QTableWidget()
        self.table_users.setColumnCount(3)
        self.table_users.setHorizontalHeaderLabels(["ID", "Usuario", "Rol"])
        self.table_users.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table_users.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table_users.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table_users.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        actions_layout = QHBoxLayout()
        self.btn_delete_user = QPushButton("Eliminar Usuario")
        self.btn_delete_user.setStyleSheet("background-color: #d9534f;")

        self.btn_reset_pass = QPushButton("Resetear Password")
        self.btn_reset_pass.setStyleSheet("background-color: #f0ad4e; color: black;")

        actions_layout.addWidget(self.btn_reset_pass)
        actions_layout.addWidget(self.btn_delete_user)

        right_panel.addWidget(lbl_list)
        right_panel.addWidget(self.table_users)
        right_panel.addLayout(actions_layout)

        layout.addLayout(left_panel, 30)
        layout.addLayout(right_panel, 70)

    def update_signature_status_label(self):
        # Este método se usa en la inicialización básica
        if self.user_data.get("signature_path"):
            self.lbl_signature_status.setText(
                "✅ Firma Digital Cargada\nLista para usar."
            )
            self.lbl_signature_status.setStyleSheet(
                "color: #00ff00; font-weight: bold;"
            )
            self.btn_process.setEnabled(True)
        else:
            self.lbl_signature_status.setText(
                "❌ NO tienes firma configurada.\nVe a la pestaña 'Mi Firma'."
            )
            self.lbl_signature_status.setStyleSheet(
                "color: #ff5555; font-weight: bold;"
            )
            self.btn_process.setEnabled(False)

    # Eventos Drag & Drop
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        event.accept()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        for f in files:
            if f.lower().endswith(".pdf"):
                self.list_files.addItem(f)
