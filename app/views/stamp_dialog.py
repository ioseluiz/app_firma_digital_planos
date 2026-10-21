"""Configuración del sello: importar escaneo, elegir región, enderezar, quitar fondo y fijar tamaño real."""
import os

from PIL import Image
from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QDoubleSpinBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QRubberBand, QVBoxLayout,
)

from app.utils import stamp_image
from app.views.styles import THEMES

MARGIN_MM = 1.0   # margen que deja el procesado automático alrededor del marco


def _label(text, role=None, wrap=True):
    lbl = QLabel(text)
    if role:
        lbl.setProperty("role", role)
    lbl.setWordWrap(wrap)
    return lbl


def pil_to_qpixmap(img):
    img = img.convert("RGBA")
    qimg = QImage(img.tobytes("raw", "RGBA"), img.width, img.height, img.width * 4,
                  QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


def checker_pixmap(pm):
    """Dibuja `pm` sobre un fondo de cuadros para ver la transparencia."""
    out = QPixmap(pm.size())
    p = QPainter(out)
    s = 10
    for y in range(0, pm.height(), s):
        for x in range(0, pm.width(), s):
            p.fillRect(x, y, s, s, QColor("#ffffff") if (x // s + y // s) % 2 == 0 else QColor("#e6e6e6"))
    p.drawPixmap(0, 0, pm)
    p.end()
    return out


class RegionSelectDialog(QDialog):
    """Muestra el escaneo para encerrar con un recuadro el sello que se quiere usar."""

    def __init__(self, img, theme, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Elige el sello en el escaneo")
        self.setStyleSheet(THEMES[theme])
        self._img = img
        self._region = None
        lay = QVBoxLayout(self)
        lay.addWidget(_label("Arrastra un recuadro alrededor del sello que quieres usar "
                             "(por ejemplo, el que salió más limpio). No hace falta que sea exacto: "
                             "luego se recorta y endereza automáticamente."))
        avail = QSize(900, 650)
        pm = pil_to_qpixmap(img).scaled(avail, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation)
        self._scale = pm.width() / img.width
        self.view = QLabel()
        self.view.setPixmap(pm)
        self.view.setFixedSize(pm.size())
        self.view.setFrameShape(QFrame.Shape.Box)
        self.view.mousePressEvent = self._press
        self.view.mouseMoveEvent = self._move
        self.view.mouseReleaseEvent = self._release
        self._band = QRubberBand(QRubberBand.Shape.Rectangle, self.view)
        self._origin = QPoint()
        lay.addWidget(self.view, alignment=Qt.AlignmentFlag.AlignCenter)
        row = QHBoxLayout()
        self.btn_all = QPushButton("Usar toda la imagen")
        self.btn_ok = QPushButton("Usar el sello seleccionado")
        self.btn_ok.setProperty("variant", "primary")
        self.btn_ok.setEnabled(False)
        self.btn_all.clicked.connect(self._use_all)
        self.btn_ok.clicked.connect(self.accept)
        row.addStretch()
        row.addWidget(self.btn_all)
        row.addWidget(self.btn_ok)
        lay.addLayout(row)

    def _press(self, e):
        self._origin = e.position().toPoint()
        self._band.setGeometry(QRect(self._origin, QSize()))
        self._band.show()

    def _move(self, e):
        self._band.setGeometry(QRect(self._origin, e.position().toPoint()).normalized())

    def _release(self, e):
        r = self._band.geometry()
        if r.width() > 10 and r.height() > 10:
            s = self._scale
            self._region = (int(r.left() / s), int(r.top() / s), int(r.right() / s), int(r.bottom() / s))
            self.btn_ok.setEnabled(True)

    def _use_all(self):
        self._region = None
        self.accept()

    def region(self):
        return self._region


class StampDialog(QDialog):
    def __init__(self, vault, theme="light", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mi sello y firma")
        self.setStyleSheet(THEMES[theme])
        self.setMinimumWidth(560)
        self._theme = theme
        self._vault = vault
        self._png = None
        self._px_size = None       # (w, h) en píxeles de la imagen
        self._margin_mm = vault.get_setting("stamp_margin_mm", 0.0)
        self._scan_path = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)
        lay.addWidget(_label("Mi sello y firma", "title"))
        lay.addWidget(_label("Sube el escaneo de tu sello con la firma. Se guarda cifrado en este equipo "
                             "y solo se usa con tu contraseña maestra.", "muted"))

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(180)
        self.preview.setFrameShape(QFrame.Shape.StyledPanel)
        lay.addWidget(self.preview)

        imp = QHBoxLayout()
        self.btn_import = QPushButton("Importar escaneo…")
        self.btn_import.clicked.connect(self._import)
        imp.addWidget(self.btn_import)
        imp.addStretch()
        lay.addLayout(imp)
        self.chk_auto = QCheckBox("Recortar y enderezar el sello automáticamente")
        self.chk_auto.setChecked(True)
        self.chk_bg = QCheckBox("Quitar el fondo blanco (transparente)")
        self.chk_bg.setChecked(True)
        lay.addWidget(self.chk_auto)
        lay.addWidget(self.chk_bg)

        size = QFrame()
        size.setProperty("card", True)
        s = QVBoxLayout(size)
        s.setContentsMargins(14, 12, 14, 12)
        s.addWidget(_label("TAMAÑO REAL", "section"))
        row = QHBoxLayout()
        row.addWidget(_label("Ancho del marco del sello, medido con regla:", wrap=False))
        self.spin_w = QDoubleSpinBox()
        self.spin_w.setRange(5, 300)
        self.spin_w.setDecimals(1)
        self.spin_w.setSuffix(" mm")
        self.spin_w.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.spin_w.setMinimumWidth(90)
        self.spin_w.valueChanged.connect(self._update_size_label)
        row.addWidget(self.spin_w)
        row.addStretch()
        s.addLayout(row)
        self.lbl_size = _label("", "muted")
        s.addWidget(self.lbl_size)
        self.chk_confirm = QCheckBox("Medí mi sello físico con una regla y el ancho coincide")
        s.addWidget(self.chk_confirm)
        lay.addWidget(size)

        self.chk_delete_scan = QCheckBox("Borrar el archivo de escaneo original (queda solo la copia cifrada)")
        self.chk_delete_scan.setVisible(False)
        lay.addWidget(self.chk_delete_scan)

        lay.addWidget(_label(
            "Protección: cada hoja sellada lleva un ID único y el sello va fundido con el fondo del plano; "
            "el PDF se bloquea contra edición y copia. Esto hace evidente y rastreable cualquier reutilización, "
            "pero ninguna medida visual impide una captura de pantalla. La protección criptográfica completa "
            "llegará con la firma digital con certificado.", "muted"))

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton("Guardar")
        self.btn_save.setProperty("variant", "primary")
        self.btn_save.clicked.connect(self._save)
        btns.addWidget(cancel)
        btns.addWidget(self.btn_save)
        lay.addLayout(btns)

        current = vault.load_stamp()
        if current:
            png, w_mm, h_mm = current
            self._set_image(png, w_mm - 2 * self._margin_mm)
            self.chk_confirm.setChecked(bool(vault.get_setting("stamp_size_confirmed", False)))
        else:
            self.preview.setText("Aún no hay sello. Importa el escaneo de tu sello con firma.")
        self.btn_save.setEnabled(self._png is not None)

    # ------------------------------------------------------------ import
    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Escaneo del sello", "",
                                              "Imágenes (*.png *.jpg *.jpeg *.tif *.tiff *.bmp)")
        if not path:
            return
        try:
            img = Image.open(path)
            img.load()
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"No se pudo abrir la imagen:\n{e}")
            return
        dpi = stamp_image.image_dpi(img)
        region = None
        if self.chk_auto.isChecked():
            sel = RegionSelectDialog(img.convert("RGB"), self._theme, self)
            if not sel.exec():
                return
            region = sel.region()
        try:
            out, dpi, info = stamp_image.prepare_scan(
                img, dpi=dpi, region=region, straighten=self.chk_auto.isChecked(),
                remove_background=self.chk_bg.isChecked())
        except ValueError as e:
            QMessageBox.warning(self, "Sello no encontrado", str(e))
            return
        self._margin_mm = MARGIN_MM if self.chk_auto.isChecked() else 0.0
        self._scan_path = path
        self.chk_delete_scan.setVisible(True)
        self.chk_confirm.setChecked(False)
        self._set_image(stamp_image.to_png_bytes(out, dpi), info["width_mm"] - 2 * self._margin_mm)
        self.btn_save.setEnabled(True)

    def _set_image(self, png, frame_w_mm):
        self._png = png
        img = stamp_image.from_bytes(png)
        self._px_size = img.size
        pm = pil_to_qpixmap(img).scaled(480, 170, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation)
        self.preview.setPixmap(checker_pixmap(pm))
        self.spin_w.blockSignals(True)
        self.spin_w.setValue(frame_w_mm)
        self.spin_w.blockSignals(False)
        self._update_size_label()

    def _total_size_mm(self):
        w_px, h_px = self._px_size
        total_w = self.spin_w.value() + 2 * self._margin_mm
        return total_w, total_w * h_px / w_px

    def _update_size_label(self):
        if not self._px_size:
            return
        tw, th = self._total_size_mm()
        frame_h = th - 2 * self._margin_mm
        self.lbl_size.setText(f"Sello: {self.spin_w.value():.1f} × {frame_h:.1f} mm "
                              f"(imagen con margen: {tw:.1f} × {th:.1f} mm). "
                              "Se insertará siempre a este tamaño, en cualquier hoja.")
        if self.sender() is self.spin_w:
            # Cambiar el tamaño invalida la confirmación con regla
            self.chk_confirm.setChecked(False)

    # ------------------------------------------------------------ save
    def _save(self):
        if not self._png:
            return
        tw, th = self._total_size_mm()
        self._vault.save_stamp(self._png, tw, th, confirmed=self.chk_confirm.isChecked())
        self._vault.set_setting("stamp_margin_mm", self._margin_mm)
        if self._scan_path and self.chk_delete_scan.isChecked():
            answer = QMessageBox.question(
                self, "Borrar escaneo",
                f"¿Borrar definitivamente el archivo original?\n\n{self._scan_path}\n\n"
                "El sello queda guardado solo en la bóveda cifrada.")
            if answer == QMessageBox.StandardButton.Yes:
                try:
                    os.remove(self._scan_path)
                except OSError as e:
                    QMessageBox.warning(self, "Aviso", f"No se pudo borrar el archivo:\n{e}")
        self.accept()
