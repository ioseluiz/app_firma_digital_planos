import fitz  # PyMuPDF
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
)
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QBrush
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint, QSize


class PDFLabel(QLabel):
    """
    Etiqueta que permite dibujar un rectangulo arrastrando el mouse.
    Emite (x, y, ancho, alto)
    """

    # Señal ahora envía 4 enteros: x, y, width, height
    selection_signal = pyqtSignal(int, int, int, int)

    def __init__(self):
        super().__init__()
        self.start_point = None
        self.end_point = None
        self.is_drawing = False
        self.current_rect = QRect()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_point = event.pos()
            self.is_drawing = True
            self.current_rect = QRect(self.start_point, self.start_point)
            self.update()

    def mouseMoveEvent(self, event):
        if self.is_drawing and self.start_point:
            self.end_point = event.pos()
            # Crear rectangulo normalizado (funciona aunque arrastres hacia atras)
            self.current_rect = QRect(self.start_point, self.end_point).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_drawing:
            self.end_point = event.pos()
            self.current_rect = QRect(self.start_point, self.end_point).normalized()
            self.is_drawing = False
            self.update()

            # Emitir coordenadas y dimensiones
            self.selection_signal.emit(
                self.current_rect.x(),
                self.current_rect.y(),
                self.current_rect.width(),
                self.current_rect.height(),
            )

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.current_rect.isNull():
            painter = QPainter(self)
            # Borde Rojo
            pen = QPen(QColor(255, 0, 0), 2)
            painter.setPen(pen)
            # Relleno semi-transparente rojo para ver mejor el area
            brush = QBrush(QColor(255, 0, 0, 50))
            painter.setBrush(brush)

            painter.drawRect(self.current_rect)
            painter.end()


class SelectorView(QDialog):
    def __init__(self, pdf_path):
        super().__init__()
        self.setWindowTitle("Dibujar Área de Firma")
        self.resize(1000, 800)
        self.pdf_path = pdf_path
        # Ahora guardamos (x, y, w, h)
        self.selected_geometry = None
        self.scale_factor = 1.0

        layout = QVBoxLayout(self)

        lbl_instr = QLabel(
            "Haz clic y arrastra para dibujar el recuadro donde irá la firma."
        )
        lbl_instr.setStyleSheet("font-size: 14px; font-weight: bold; color: #555;")
        layout.addWidget(lbl_instr)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.pdf_label = PDFLabel()
        self.pdf_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.pdf_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        # Conectar nueva señal
        self.pdf_label.selection_signal.connect(self.handle_selection)

        self.scroll_area.setWidget(self.pdf_label)
        layout.addWidget(self.scroll_area)

        self.btn_confirm = QPushButton("Confirmar Área")
        self.btn_confirm.setEnabled(False)
        self.btn_confirm.clicked.connect(self.accept)
        self.btn_confirm.setStyleSheet(
            "background-color: #007acc; color: white; padding: 10px; font-weight: bold;"
        )

        layout.addWidget(self.btn_confirm)

        self.load_pdf_image()

    def load_pdf_image(self):
        try:
            doc = fitz.open(self.pdf_path)
            page = doc[0]

            # Zoom x2 para buena calidad al dibujar
            zoom = 2.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)

            img_format = QImage.Format.Format_RGB888
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, img_format)

            self.pdf_label.setPixmap(QPixmap.fromImage(img))

            self.scale_factor = zoom
            doc.close()
        except Exception as e:
            print(f"Error al cargar PDF: {str(e)}")

    def handle_selection(self, x, y, w, h):
        # Convertir todo usando el factor de escala
        real_x = x / self.scale_factor
        real_y = y / self.scale_factor
        real_w = w / self.scale_factor
        real_h = h / self.scale_factor

        self.selected_geometry = (real_x, real_y, real_w, real_h)

        self.btn_confirm.setEnabled(True)
        self.btn_confirm.setText(
            f"Confirmar Área (X:{int(real_x)}, Y:{int(real_y)} - {int(real_w)}x{int(real_h)})"
        )

    def get_geometry(self):
        return self.selected_geometry
