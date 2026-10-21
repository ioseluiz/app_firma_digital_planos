"""Panel derecho: hoja actual, sello de la hoja (posición/ángulo), copiar, datos del ID y salida."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from app.models.placement import PROFILE_PLAN, PROFILE_REPORT
from app.utils import geometry
from app.views.icons import icon


def _label(text, role=None, wrap=False):
    lbl = QLabel(text)
    if role:
        lbl.setProperty("role", role)
    lbl.setWordWrap(wrap)
    return lbl


def _card(title):
    frame = QFrame()
    frame.setProperty("card", True)
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(14, 12, 14, 14)
    lay.setSpacing(8)
    lay.addWidget(_label(title.upper(), "section"))
    return frame, lay


class PropertiesPanel(QScrollArea):
    place_clicked = pyqtSignal()
    remove_clicked = pyqtSignal()
    reset_clicked = pyqtSignal()
    rotate_by_clicked = pyqtSignal(float)
    values_edited = pyqtSignal(float, float, float)        # cx_pt, cy_pt, rot
    copy_selected_clicked = pyqtSignal()
    copy_file_clicked = pyqtSignal()
    copy_all_clicked = pyqtSignal()
    profile_changed = pyqtSignal(str)
    project_changed = pyqtSignal(str, str)                # proyecto, expediente
    output_dir_clicked = pyqtSignal()
    output_dir_reset_clicked = pyqtSignal()
    stamp_settings_clicked = pyqtSignal()

    def __init__(self, tokens, parent=None):
        super().__init__(parent)
        self._tokens = tokens
        self._updating = False
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        self.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)

        # --- Hoja ---------------------------------------------------------
        card, c = _card("Hoja")
        self.lbl_page = _label("Ninguna hoja seleccionada", "heading", wrap=True)
        self.lbl_format = _label("", "muted", wrap=True)
        row = QHBoxLayout()
        row.addWidget(_label("Tipo de documento:"))
        self.cmb_profile = QComboBox()
        self.cmb_profile.addItem("Plano · todas las hojas", PROFILE_PLAN)
        self.cmb_profile.addItem("Reporte · última hoja", PROFILE_REPORT)
        self.cmb_profile.setToolTip("Define dónde se coloca el sello inicialmente en este archivo.\n"
                                    "Cambiarlo restablece las posiciones de sus hojas.")
        self.cmb_profile.activated.connect(
            lambda i: self._updating or self.profile_changed.emit(self.cmb_profile.itemData(i)))
        row.addWidget(self.cmb_profile, 1)
        self.lbl_page_status = _label("", "warning", wrap=True)
        c.addWidget(self.lbl_page)
        c.addWidget(self.lbl_format)
        c.addLayout(row)
        c.addWidget(self.lbl_page_status)
        lay.addWidget(card)

        # --- Sello de esta hoja -------------------------------------------
        card, c = _card("Sello en esta hoja")
        self.lbl_rule = _label("Regla: máximo un sello por hoja.", "muted", wrap=True)
        c.addWidget(self.lbl_rule)
        self.btn_place = QPushButton("Colocar sello en esta hoja")
        self.btn_place.clicked.connect(self.place_clicked)
        c.addWidget(self.btn_place)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        self.spin_x = self._spin(" mm", 0, 5000, 1)
        self.spin_y = self._spin(" mm", 0, 5000, 1)
        self.spin_rot = self._spin("°", 0, 360, 1)
        self.spin_rot.setWrapping(True)
        grid.addWidget(_label("Centro X"), 0, 0)
        grid.addWidget(self.spin_x, 0, 1)
        grid.addWidget(_label("Centro Y"), 1, 0)
        grid.addWidget(self.spin_y, 1, 1)
        grid.addWidget(_label("Ángulo"), 2, 0)
        grid.addWidget(self.spin_rot, 2, 1)
        c.addLayout(grid)
        c.addWidget(_label("X/Y desde la esquina superior izquierda de la hoja. "
                           "Arrastra el sello o su asa circular para moverlo o rotarlo.", "muted", wrap=True))

        rot_row = QHBoxLayout()
        self.btn_rot_ccw = QPushButton(" 90°")
        self.btn_rot_cw = QPushButton(" 90°")
        self.btn_rot_ccw.setToolTip("Rotar 90° a la izquierda (Shift+R)")
        self.btn_rot_cw.setToolTip("Rotar 90° a la derecha (R)")
        self.btn_rot_ccw.clicked.connect(lambda: self.rotate_by_clicked.emit(-90.0))
        self.btn_rot_cw.clicked.connect(lambda: self.rotate_by_clicked.emit(90.0))
        rot_row.addWidget(self.btn_rot_ccw)
        rot_row.addWidget(self.btn_rot_cw)
        c.addLayout(rot_row)

        act_row = QHBoxLayout()
        self.btn_reset = QPushButton(" Restablecer")
        self.btn_reset.setToolTip("Volver a la posición inicial según el tipo de documento")
        self.btn_reset.clicked.connect(self.reset_clicked)
        self.btn_remove = QPushButton(" Quitar")
        self.btn_remove.setProperty("variant", "danger")
        self.btn_remove.setToolTip("Quitar el sello de esta hoja (Supr)")
        self.btn_remove.clicked.connect(self.remove_clicked)
        act_row.addWidget(self.btn_reset)
        act_row.addWidget(self.btn_remove)
        c.addLayout(act_row)
        lay.addWidget(card)
        self._stamp_widgets = [self.spin_x, self.spin_y, self.spin_rot, self.btn_rot_ccw,
                               self.btn_rot_cw, self.btn_reset, self.btn_remove]

        # --- Copiar a otras hojas -----------------------------------------
        card, c = _card("Copiar posición y ángulo a…")
        self.btn_copy_sel = QPushButton("Hojas seleccionadas")
        self.btn_copy_file = QPushButton("Todo este archivo")
        self.btn_copy_all = QPushButton("Todos los archivos")
        self.btn_copy_sel.setToolTip("Selecciona varias hojas en la lista con Ctrl/Shift + clic")
        self.btn_copy_sel.clicked.connect(self.copy_selected_clicked)
        self.btn_copy_file.clicked.connect(self.copy_file_clicked)
        self.btn_copy_all.clicked.connect(self.copy_all_clicked)
        for b in (self.btn_copy_sel, self.btn_copy_file, self.btn_copy_all):
            c.addWidget(b)
        c.addWidget(_label("Reemplaza la posición del sello en esas hojas; nunca añade un segundo sello. "
                           "Cada hoja sigue siendo independiente después.", "muted", wrap=True))
        lay.addWidget(card)
        self._copy_widgets = [self.btn_copy_sel, self.btn_copy_file, self.btn_copy_all]

        # --- Datos para el ID ---------------------------------------------
        card, c = _card("Datos impresos con el ID")
        self.txt_project = QLineEdit()
        self.txt_project.setPlaceholderText("Proyecto (opcional)")
        self.txt_exp = QLineEdit()
        self.txt_exp.setPlaceholderText("Nº de expediente (opcional, va en metadatos)")
        for w in (self.txt_project, self.txt_exp):
            w.editingFinished.connect(
                lambda: self.project_changed.emit(self.txt_project.text().strip(), self.txt_exp.text().strip()))
            c.addWidget(w)
        c.addWidget(_label("Bajo cada sello se imprime: Proyecto · Hoja n/N · fecha · ID único.",
                           "muted", wrap=True))
        lay.addWidget(card)

        # --- Mi sello -----------------------------------------------------
        card, c = _card("Mi sello")
        self.lbl_stamp_preview = QLabel()
        self.lbl_stamp_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_stamp_preview.setMinimumHeight(70)
        self.lbl_stamp_size = _label("", "muted", wrap=True)
        self.lbl_stamp_warn = _label("", "warning", wrap=True)
        self.btn_stamp = QPushButton(" Configurar sello…")
        self.btn_stamp.clicked.connect(self.stamp_settings_clicked)
        c.addWidget(self.lbl_stamp_preview)
        c.addWidget(self.lbl_stamp_size)
        c.addWidget(self.lbl_stamp_warn)
        c.addWidget(self.btn_stamp)
        lay.addWidget(card)

        # --- Salida -------------------------------------------------------
        card, c = _card("Carpeta de salida")
        self.lbl_output = _label("Misma carpeta que cada original", "muted", wrap=True)
        out_row = QHBoxLayout()
        self.btn_output = QPushButton(" Cambiar…")
        self.btn_output.clicked.connect(self.output_dir_clicked)
        self.btn_output_reset = QPushButton("Usar la del original")
        self.btn_output_reset.setProperty("variant", "link")
        self.btn_output_reset.clicked.connect(self.output_dir_reset_clicked)
        out_row.addWidget(self.btn_output)
        out_row.addWidget(self.btn_output_reset)
        out_row.addStretch()
        c.addWidget(self.lbl_output)
        c.addLayout(out_row)
        c.addWidget(_label("Los archivos se guardan como SELLADO_<nombre>.pdf; el original no se modifica.",
                           "muted", wrap=True))
        lay.addWidget(card)

        lay.addStretch()
        self.set_tokens(tokens)
        self.show_page(None, None, None, False)

    def _spin(self, suffix, lo, hi, decimals):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(decimals)
        s.setSuffix(suffix)
        s.setKeyboardTracking(False)
        s.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        s.setToolTip("Escribe el valor, o usa la rueda del ratón / flechas ↑↓")
        s.setMinimumHeight(30)
        s.valueChanged.connect(self._emit_values)
        return s

    def _emit_values(self, *_):
        if self._updating:
            return
        self.values_edited.emit(geometry.mm_to_pt(self.spin_x.value()),
                                geometry.mm_to_pt(self.spin_y.value()),
                                self.spin_rot.value() % 360.0)

    # ------------------------------------------------------------ updates
    def set_tokens(self, tokens):
        self._tokens = tokens
        muted = tokens["text"]
        self.btn_rot_ccw.setIcon(icon("rotate_ccw", muted))
        self.btn_rot_cw.setIcon(icon("rotate_cw", muted))
        self.btn_reset.setIcon(icon("reset", muted))
        self.btn_remove.setIcon(icon("trash", tokens["danger"]))
        self.btn_place.setIcon(icon("place", muted))
        self.btn_stamp.setIcon(icon("settings", muted))
        self.btn_output.setIcon(icon("folder", muted))
        for b in self._copy_widgets:
            b.setIcon(icon("copy", muted))

    def show_page(self, doc, page, placement, locked, total_pages=None):
        self._updating = True
        try:
            has_page = page is not None
            if has_page:
                self.lbl_page.setText(f"{doc.name}\nHoja {page.index + 1} de {len(doc.pages)}")
                w_mm, h_mm = geometry.pt_to_mm(page.width), geometry.pt_to_mm(page.height)
                fmt = geometry.detect_format(page.width, page.height)
                warn = "" if fmt else "  ·  formato no estándar: imprimir al 100 %"
                self.lbl_format.setText(f"{page.format_name} · {w_mm:.0f} × {h_mm:.0f} mm{warn}")
                self.cmb_profile.setCurrentIndex(0 if doc.profile == PROFILE_PLAN else 1)
            else:
                self.lbl_page.setText("Ninguna hoja seleccionada")
                self.lbl_format.setText("Abre o arrastra PDFs para empezar.")
            self.cmb_profile.setEnabled(has_page)
            self.lbl_page_status.setText(
                "Esta hoja ya fue sellada por DigitalSealer y está bloqueada: no admite otro sello."
                if locked else "")
            self.lbl_page_status.setVisible(bool(locked))

            can_edit = has_page and not locked
            has_stamp = placement is not None
            self.btn_place.setVisible(can_edit and not has_stamp)
            for w in self._stamp_widgets:
                w.setEnabled(can_edit and has_stamp)
            for w in self._copy_widgets:
                w.setEnabled(can_edit and has_stamp)
            if has_page:
                self.spin_x.setMaximum(geometry.pt_to_mm(page.width))
                self.spin_y.setMaximum(geometry.pt_to_mm(page.height))
            if has_stamp:
                self.spin_x.setValue(geometry.pt_to_mm(placement.cx))
                self.spin_y.setValue(geometry.pt_to_mm(placement.cy))
                self.spin_rot.setValue(placement.rotation)
            else:
                self.spin_x.setValue(0)
                self.spin_y.setValue(0)
                self.spin_rot.setValue(0)
        finally:
            self._updating = False

    def show_live(self, cx, cy, rot):
        """Actualiza los valores mientras se arrastra/rota (sin emitir ediciones)."""
        self._updating = True
        try:
            self.spin_x.setValue(geometry.pt_to_mm(cx))
            self.spin_y.setValue(geometry.pt_to_mm(cy))
            self.spin_rot.setValue(rot)
        finally:
            self._updating = False

    def set_project(self, project, expediente):
        self.txt_project.setText(project or "")
        self.txt_exp.setText(expediente or "")

    def set_output_dir(self, path):
        self.lbl_output.setText(path or "Misma carpeta que cada original")
        self.btn_output_reset.setVisible(bool(path))

    def set_stamp_info(self, png_bytes, w_mm, h_mm, confirmed):
        if not png_bytes:
            self.lbl_stamp_preview.clear()
            self.lbl_stamp_size.setText("No hay sello configurado.")
            self.lbl_stamp_warn.setText("Configura tu sello para poder sellar.")
            return
        pm = QPixmap()
        pm.loadFromData(png_bytes)
        pm = pm.scaled(240, 90, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        bg = QPixmap(pm.size())
        bg.fill(QColor("white"))
        p = QPainter(bg)
        p.drawPixmap(0, 0, pm)
        p.end()
        self.lbl_stamp_preview.setPixmap(bg)
        self.lbl_stamp_size.setText(f"Tamaño real: {w_mm:.1f} × {h_mm:.1f} mm")
        self.lbl_stamp_warn.setText("" if confirmed else
                                    "Confirma el tamaño midiendo tu sello con una regla (Configurar sello).")
