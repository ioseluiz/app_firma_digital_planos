from PyQt6.QtWidgets import (
    QFileDialog,
    QMessageBox,
    QTableWidgetItem,
    QInputDialog,
    QLineEdit,
    QStyle 
)
from PyQt6.QtGui import QIcon, QColor 
from PyQt6.QtCore import Qt # Necesario para guardar datos en items

from app.views.main_view import MainView
from app.views.login_view import LoginView
from app.views.selector_view import SelectorView
from app.models.user_model import UserModel
from app.utils.pdf_stamper import PDFStamper
import os
import shutil
from app.utils.paths import get_app_data_path
from app.workers.signing_worker import SigningWorker

class MainController:
    def __init__(self):
        self.user_model = UserModel()
        self.login_view = None
        self.main_view = None
        self.current_user = None
        self.worker = None 

        self.is_dark_mode = True
        self.output_directory = None
        self.custom_coords = None

    def start(self):
        self.login_view = LoginView()
        self.login_view.btn_login.clicked.connect(self.handle_login)
        self.login_view.exec()

    def handle_login(self):
        username, password = self.login_view.get_credentials()
        user = self.user_model.authenticate(username, password)

        if user:
            self.current_user = user
            self.login_view.accept()
            self.show_main_window()
        else:
            self.login_view.show_error("Usuario o contraseña incorrectos")

    def show_main_window(self):
        self.main_view = MainView(self.current_user)

        self.main_view.btn_logout.clicked.connect(self.logout)
        self.main_view.btn_toggle_theme.clicked.connect(self.toggle_theme)

        # Pestaña Firma
        self.main_view.btn_add_files.clicked.connect(self.select_files)
        self.main_view.btn_clear.clicked.connect(self.main_view.list_files.clear)
        self.main_view.btn_select_output.clicked.connect(self.select_output_folder)
        self.main_view.btn_set_coords.clicked.connect(self.open_coordinate_selector)
        self.main_view.btn_process.clicked.connect(self.process_signing)
        
        # --- NUEVA CONEXIÓN: DOBLE CLIC PARA EDITAR ---
        self.main_view.list_files.itemDoubleClicked.connect(self.edit_single_file_position)

        if hasattr(self.main_view, "btn_upload_sig"):
            self.main_view.btn_upload_sig.clicked.connect(self.upload_signature)
            existing_sig = self.current_user.get("signature_path")
            if existing_sig:
                self.main_view.set_signature_image(existing_sig)

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
            self.main_view.lbl_output_dir.setStyleSheet("color: #00aaff; font-weight: bold; font-size: 11px;")

    def open_coordinate_selector(self):
        """Define la posición global (por defecto)"""
        if self.main_view.list_files.count() == 0:
            QMessageBox.warning(self.main_view, "Atención", "Primero agrega archivos PDF.")
            return

        ref_pdf_path = self.main_view.list_files.item(0).text()
        selector = SelectorView(ref_pdf_path)

        if selector.exec():
            geometry = selector.get_geometry()
            if geometry:
                self.custom_coords = geometry
                x, y, w, h = geometry
                self.main_view.lbl_coords_status.setText(f"Posición Global: X={int(x)}, Y={int(y)}")
                self.main_view.lbl_coords_status.setStyleSheet("color: #00aaff; font-weight: bold;")
            else:
                self.custom_coords = None
                self.main_view.lbl_coords_status.setText("Posición: Predeterminada")
                self.main_view.lbl_coords_status.setStyleSheet("color: #888;")

    # --- NUEVO MÉTODO: EDITOR INDIVIDUAL ---
    def edit_single_file_position(self, item):
        """Abre el selector solo para el archivo seleccionado"""
        # Obtenemos la ruta. Si ya tiene alias, la ruta real está en UserRole+1
        pdf_path = item.data(Qt.ItemDataRole.UserRole + 1)
        if not pdf_path:
            pdf_path = item.text()
        
        # 1. ¿Tiene coords propias ya guardadas?
        current_coords = item.data(Qt.ItemDataRole.UserRole)
        
        # 2. Si no, ¿usamos las globales?
        if not current_coords:
            current_coords = self.custom_coords
            
        # 3. Si no, usamos default (400, 700...) para pintar algo
        if not current_coords:
            current_coords = (400, 700, 150, 60)

        # Abrir Selector pasando las coordenadas actuales para pre-visualizar
        selector = SelectorView(pdf_path, initial_coords=current_coords)
        
        if selector.exec():
            new_coords = selector.get_geometry()
            if new_coords:
                # GUARDAMOS LAS COORDENADAS EN EL ÍTEM MISMO
                item.setData(Qt.ItemDataRole.UserRole, new_coords)
                
                # Feedback visual en la lista
                base_name = os.path.basename(pdf_path)
                item.setText(f"{base_name} (Posición Personalizada ✏️)")
                item.setToolTip(f"Coordenadas personalizadas: {new_coords}")
                
                # Guardamos la ruta real en otro rol para no perderla al cambiar el texto
                item.setData(Qt.ItemDataRole.UserRole + 1, pdf_path) 
                
                # Quitamos iconos de estado anteriores
                item.setIcon(QIcon())
                item.setBackground(QColor(0,0,0,0))

    def upload_signature(self):
        file, _ = QFileDialog.getOpenFileName(self.main_view, "Seleccionar Firma", "", "Images (*.png *.jpg *.jpeg)")
        if file:
            app_data = get_app_data_path()
            sig_folder = os.path.join(app_data, "signatures")
            if not os.path.exists(sig_folder): os.makedirs(sig_folder)
            
            file_ext = os.path.splitext(file)[1]
            new_filename = f"sig_user_{self.current_user['id']}{file_ext}"
            destination = os.path.join(sig_folder, new_filename)
            try:
                shutil.copy2(file, destination)
            except Exception as e:
                QMessageBox.critical(self.main_view, "Error", f"No se pudo guardar: {e}")
                return

            self.user_model.update_signature(self.current_user['id'], destination)
            self.current_user['signature_path'] = destination
            self.main_view.user_data['signature_path'] = destination
            self.main_view.set_signature_image(destination)
            QMessageBox.information(self.main_view, "Éxito", "Firma guardada correctamente.")

    def process_signing(self):
        sig_path = self.current_user["signature_path"]
        if not sig_path or not os.path.exists(sig_path):
            QMessageBox.critical(self.main_view, "Error", "Archivo de firma no encontrado.")
            return

        count = self.main_view.list_files.count()
        if count == 0:
            QMessageBox.warning(self.main_view, "Atención", "No has seleccionado ningún archivo PDF.")
            return
        
        # CONSTRUIR LA LISTA DE TAREAS INTELIGENTE
        work_queue = []
        
        for i in range(count):
            item = self.main_view.list_files.item(i)
            
            # Recuperar ruta (priorizando la data oculta si se editó el nombre)
            path = item.data(Qt.ItemDataRole.UserRole + 1)
            if not path:
                path = item.text()

            # Recuperar Coordenadas (Prioridad: Individual > Global > Default)
            coords = item.data(Qt.ItemDataRole.UserRole)
            if not coords:
                coords = self.custom_coords # Globales
            
            # Limpiar estado visual
            item.setIcon(QIcon())
            item.setBackground(QColor(0,0,0,0))
            if "Personalizada" not in item.text():
                 item.setToolTip("")
            
            # Agregar a la cola: Objeto con path y coords
            work_queue.append({
                'path': path,
                'coords': coords, 
                'list_index': i
            })

        self.main_view.btn_process.setEnabled(False)
        self.main_view.btn_clear.setEnabled(False)
        self.main_view.progress_bar.setVisible(True)
        self.main_view.progress_bar.setValue(0)
        self.main_view.lbl_process_status.setText("Iniciando motor de firma...")

        # INICIAR WORKER CON LA NUEVA ESTRUCTURA
        self.worker = SigningWorker(
            work_queue=work_queue, # Pasamos la cola inteligente
            sig_path=sig_path,
            output_dir=self.output_directory
        )
        
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.status_updated.connect(self.update_status_label)
        self.worker.finished_signal.connect(self.on_signing_finished)
        self.worker.file_processed.connect(self.on_file_processed)
        
        self.worker.start()

    def update_progress(self, val):
        self.main_view.progress_bar.setValue(val)

    def update_status_label(self, text):
        self.main_view.lbl_process_status.setText(text)
    
    def on_file_processed(self, index, success, msg):
        item = self.main_view.list_files.item(index)
        if success:
            icon = self.main_view.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton)
            item.setIcon(icon)
            tooltip_prev = item.toolTip()
            item.setToolTip(f"✅ Firmado correctamente. {tooltip_prev}")
        else:
            icon = self.main_view.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxCritical)
            item.setIcon(icon)
            bg_color = QColor("#500000") if self.is_dark_mode else QColor("#ffe6e6")
            item.setBackground(bg_color)
            item.setToolTip(f"❌ ERROR: {msg}")

    def on_signing_finished(self, report_msg):
        self.main_view.btn_process.setEnabled(True)
        self.main_view.btn_clear.setEnabled(True)
        self.main_view.lbl_process_status.setText("Proceso finalizado")
        self.main_view.progress_bar.setVisible(False)
        QMessageBox.information(self.main_view, "Reporte Final", report_msg)
        self.worker = None

    # --- CRUD USUARIOS (Sin cambios) ---
    def load_user_list(self):
        users = self.user_model.get_all_users()
        self.main_view.table_users.setRowCount(0)
        for row_idx, user_data in enumerate(users):
            self.main_view.table_users.insertRow(row_idx)
            self.main_view.table_users.setItem(row_idx, 0, QTableWidgetItem(str(user_data[0])))
            self.main_view.table_users.setItem(row_idx, 1, QTableWidgetItem(str(user_data[1])))
            self.main_view.table_users.setItem(row_idx, 2, QTableWidgetItem(str(user_data[2])))

    def create_user(self):
        u = self.main_view.txt_new_user.text()
        p = self.main_view.txt_new_pass.text()
        r = self.main_view.cmb_role.currentText()
        if u and p:
            if self.user_model.create_user(u, p, r):
                QMessageBox.information(self.main_view, "Éxito", f"Usuario '{u}' creado.")
                self.main_view.txt_new_user.clear()
                self.main_view.txt_new_pass.clear()
                self.load_user_list()
            else:
                QMessageBox.warning(self.main_view, "Error", "No se pudo crear.")
        else:
            QMessageBox.warning(self.main_view, "Error", "Datos incompletos.")

    def delete_user(self):
        selected_rows = self.main_view.table_users.selectionModel().selectedRows()
        if not selected_rows: return
        row = selected_rows[0].row()
        user_id = int(self.main_view.table_users.item(row, 0).text())
        if user_id == self.current_user["id"]:
            QMessageBox.critical(self.main_view, "Error", "No puedes eliminar tu cuenta.")
            return
        if self.user_model.delete_user(user_id):
            self.load_user_list()
            QMessageBox.information(self.main_view, "Éxito", "Usuario eliminado.")

    def reset_user_password(self):
        selected_rows = self.main_view.table_users.selectionModel().selectedRows()
        if not selected_rows: return
        row = selected_rows[0].row()
        user_id = int(self.main_view.table_users.item(row, 0).text())
        new_pass, ok = QInputDialog.getText(self.main_view, "Reset", "Nueva contraseña:", QLineEdit.EchoMode.Normal)
        if ok and new_pass:
            if self.user_model.reset_password(user_id, new_pass):
                QMessageBox.information(self.main_view, "Éxito", "Contraseña actualizada.")