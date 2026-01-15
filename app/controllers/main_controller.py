from PyQt6.QtWidgets import (
    QFileDialog,
    QMessageBox,
    QTableWidgetItem,
    QInputDialog,
    QLineEdit,
)
from app.views.main_view import MainView
from app.views.login_view import LoginView
from app.views.selector_view import SelectorView
from app.models.user_model import UserModel
from app.utils.pdf_stamper import PDFStamper
import os


class MainController:
    def __init__(self):
        self.user_model = UserModel()
        self.login_view = None
        self.main_view = None
        self.current_user = None

        # Estado de la aplicación
        self.is_dark_mode = True
        self.output_directory = None

        # Almacena la tupla (x, y, width, height) si el usuario define un área
        self.custom_coords = None

    def start(self):
        """Inicia el flujo de la aplicación mostrando el Login"""
        self.login_view = LoginView()
        self.login_view.btn_login.clicked.connect(self.handle_login)
        self.login_view.exec()

    def handle_login(self):
        """Valida las credenciales del usuario"""
        username, password = self.login_view.get_credentials()
        user = self.user_model.authenticate(username, password)

        if user:
            self.current_user = user
            self.login_view.accept()
            self.show_main_window()
        else:
            self.login_view.show_error("Usuario o contraseña incorrectos")

    def show_main_window(self):
        """Configura y muestra la ventana principal según el rol"""
        self.main_view = MainView(self.current_user)

        # --- CONEXIONES GENERALES ---
        self.main_view.btn_logout.clicked.connect(self.logout)
        self.main_view.btn_toggle_theme.clicked.connect(self.toggle_theme)

        # Pestaña Firma
        self.main_view.btn_add_files.clicked.connect(self.select_files)
        self.main_view.btn_clear.clicked.connect(self.main_view.list_files.clear)
        self.main_view.btn_select_output.clicked.connect(self.select_output_folder)
        self.main_view.btn_set_coords.clicked.connect(self.open_coordinate_selector)
        self.main_view.btn_process.clicked.connect(self.process_signing)

        # Pestaña Configuración (Solo Ingenieros)
        if hasattr(self.main_view, "btn_upload_sig"):
            self.main_view.btn_upload_sig.clicked.connect(self.upload_signature)

            # Cargar firma existente visualmente
            existing_sig = self.current_user.get("signature_path")
            if existing_sig:
                self.main_view.set_signature_image(existing_sig)

        # Pestaña Admin
        if self.current_user["role"] == "admin":
            self.main_view.btn_create_user.clicked.connect(self.create_user)
            self.main_view.btn_delete_user.clicked.connect(self.delete_user)
            self.main_view.btn_reset_pass.clicked.connect(self.reset_user_password)
            self.load_user_list()

        self.main_view.show()

    def logout(self):
        self.main_view.close()
        self.current_user = None
        self.start()

    def toggle_theme(self):
        if self.is_dark_mode:
            self.main_view.set_theme("light")
            self.is_dark_mode = False
        else:
            self.main_view.set_theme("dark")
            self.is_dark_mode = True

    # --------------------------------------------------------------------------
    # LÓGICA DE FIRMA Y ARCHIVOS
    # --------------------------------------------------------------------------
    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self.main_view, "Seleccionar Planos", "", "PDF Files (*.pdf)"
        )
        if files:
            self.main_view.list_files.addItems(files)

    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self.main_view, "Seleccionar Carpeta de Destino"
        )
        if folder:
            self.output_directory = folder
            self.main_view.lbl_output_dir.setText(f"Destino: {folder}")
            self.main_view.lbl_output_dir.setStyleSheet(
                "color: #00aaff; font-weight: bold; font-size: 11px;"
            )

    def open_coordinate_selector(self):
        """Abre la ventana para dibujar el área de firma"""
        if self.main_view.list_files.count() == 0:
            QMessageBox.warning(
                self.main_view,
                "Atención",
                "Primero agrega archivos PDF a la lista.\nUsaremos el primero como referencia.",
            )
            return

        ref_pdf_path = self.main_view.list_files.item(0).text()
        selector = SelectorView(ref_pdf_path)

        if selector.exec():
            # Obtenemos 4 valores: x, y, width, height
            geometry = selector.get_geometry()

            if geometry:
                self.custom_coords = geometry
                x, y, w, h = geometry

                # Actualizar etiqueta en la vista
                self.main_view.lbl_coords_status.setText(
                    f"Posición: X={int(x)}, Y={int(y)} | Tam: {int(w)}x{int(h)}"
                )
                self.main_view.lbl_coords_status.setStyleSheet(
                    "color: #00aaff; font-weight: bold;"
                )
            else:
                self.custom_coords = None
                self.main_view.lbl_coords_status.setText("Posición: Predeterminada")
                self.main_view.lbl_coords_status.setStyleSheet("color: #888;")

    def upload_signature(self):
        file, _ = QFileDialog.getOpenFileName(
            self.main_view, "Seleccionar Firma", "", "Images (*.png *.jpg *.jpeg)"
        )
        if file:
            self.user_model.update_signature(self.current_user["id"], file)
            self.current_user["signature_path"] = file
            self.main_view.user_data["signature_path"] = file
            self.main_view.set_signature_image(file)
            QMessageBox.information(
                self.main_view, "Éxito", "Firma cargada correctamente"
            )

    def process_signing(self):
        sig_path = self.current_user["signature_path"]
        if not sig_path or not os.path.exists(sig_path):
            QMessageBox.critical(
                self.main_view, "Error", "Archivo de firma no encontrado."
            )
            return

        count = self.main_view.list_files.count()
        if count == 0:
            QMessageBox.warning(
                self.main_view, "Atención", "No has seleccionado ningún archivo PDF."
            )
            return

        # Valores por defecto (si no se usa el selector visual)
        final_x, final_y = 400, 700
        final_w, final_h = 150, 60

        # Si el usuario definió un área personalizada, sobrescribimos
        if self.custom_coords:
            final_x, final_y, final_w, final_h = self.custom_coords

        success_count = 0
        errors = []
        final_dest = (
            self.output_directory
            if self.output_directory
            else "Carpeta de origen de cada archivo"
        )

        for i in range(count):
            pdf_path = self.main_view.list_files.item(i).text()
            dir_name, file_name = os.path.split(pdf_path)

            # Definir ruta de salida
            if self.output_directory:
                target_dir = self.output_directory
            else:
                target_dir = dir_name

            output_path = os.path.join(target_dir, f"SIGNED_{file_name}")

            # Pasamos las coordenadas y dimensiones dinámicas
            ok, msg = PDFStamper.stamp_pdf(
                pdf_path,
                sig_path,
                output_path,
                x=final_x,
                y=final_y,
                width=final_w,
                height=final_h,
            )

            if ok:
                success_count += 1
                self.user_model.log_action(
                    self.current_user["id"], "SIGN_PDF", file_name
                )
            else:
                errors.append(f"{file_name}: {msg}")

        msg = f"Proceso terminado.\n\n"
        msg += f"📄 Firmados: {success_count}/{count}\n"
        msg += f"📏 Dimensiones: {int(final_w)}x{int(final_h)}\n"
        msg += f"📂 Ubicación: {final_dest}\n"

        if errors:
            msg += "\n⚠️ Errores encontrados:\n" + "\n".join(errors)

        QMessageBox.information(self.main_view, "Reporte de Firma", msg)
        self.main_view.list_files.clear()

    # --------------------------------------------------------------------------
    # LÓGICA DE ADMINISTRACIÓN (CRUD)
    # --------------------------------------------------------------------------
    def load_user_list(self):
        users = self.user_model.get_all_users()
        self.main_view.table_users.setRowCount(0)
        for row_idx, user_data in enumerate(users):
            self.main_view.table_users.insertRow(row_idx)
            self.main_view.table_users.setItem(
                row_idx, 0, QTableWidgetItem(str(user_data[0]))
            )
            self.main_view.table_users.setItem(
                row_idx, 1, QTableWidgetItem(str(user_data[1]))
            )
            self.main_view.table_users.setItem(
                row_idx, 2, QTableWidgetItem(str(user_data[2]))
            )

    def create_user(self):
        u = self.main_view.txt_new_user.text()
        p = self.main_view.txt_new_pass.text()
        r = self.main_view.cmb_role.currentText()
        if u and p:
            if self.user_model.create_user(u, p, r):
                QMessageBox.information(
                    self.main_view, "Éxito", f"Usuario '{u}' creado."
                )
                self.main_view.txt_new_user.clear()
                self.main_view.txt_new_pass.clear()
                self.load_user_list()
            else:
                QMessageBox.warning(
                    self.main_view, "Error", "No se pudo crear el usuario."
                )
        else:
            QMessageBox.warning(self.main_view, "Error", "Datos incompletos.")

    def delete_user(self):
        selected_rows = self.main_view.table_users.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self.main_view, "Atención", "Selecciona un usuario.")
            return
        row = selected_rows[0].row()
        user_id = int(self.main_view.table_users.item(row, 0).text())
        if user_id == self.current_user["id"]:
            QMessageBox.critical(
                self.main_view, "Error", "No puedes eliminar tu propia cuenta."
            )
            return
        if self.user_model.delete_user(user_id):
            self.load_user_list()
            QMessageBox.information(self.main_view, "Éxito", "Usuario eliminado.")

    def reset_user_password(self):
        selected_rows = self.main_view.table_users.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self.main_view, "Atención", "Selecciona un usuario.")
            return
        row = selected_rows[0].row()
        user_id = int(self.main_view.table_users.item(row, 0).text())
        new_pass, ok = QInputDialog.getText(
            self.main_view,
            "Reset Password",
            "Nueva contraseña:",
            QLineEdit.EchoMode.Normal,
        )
        if ok and new_pass:
            if self.user_model.reset_password(user_id, new_pass):
                QMessageBox.information(
                    self.main_view, "Éxito", "Contraseña actualizada."
                )
