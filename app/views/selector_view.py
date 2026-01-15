import fitz  # PyMuPDF
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QBrush
from PyQt6.QtCore import Qt, pyqtSignal, QRect

class PDFLabel(QLabel):
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
            self.current_rect = QRect(self.start_point, self.end_point).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_drawing:
            self.end_point = event.pos()
            self.current_rect = QRect(self.start_point, self.end_point).normalized()
            self.is_drawing = False
            self.update()
            
            self.selection_signal.emit(
                self.current_rect.x(), self.current_rect.y(),
                self.current_rect.width(), self.current_rect.height()
            )

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.current_rect.isNull():
            painter = QPainter(self)
            painter.setPen(QPen(QColor(255, 0, 0), 2))
            painter.setBrush(QBrush(QColor(255, 0, 0, 50)))
            painter.drawRect(self.current_rect)
            painter.end()

class SelectorView(QDialog):
    def __init__(self, pdf_path):
        super().__init__()
        self.setWindowTitle("Selector Final - Posición Restaurada")
        self.resize(1000, 800)
        self.pdf_path = pdf_path
        self.selected_geometry = None 
        self.scale_factor = 1.0 
        self.page_rotation = 0
        self.page_rect = None

        layout = QVBoxLayout(self)
        lbl_instr = QLabel("Haz clic y arrastra para dibujar el recuadro donde irá la firma.")
        layout.addWidget(lbl_instr)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        
        self.pdf_label = PDFLabel()
        self.pdf_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.pdf_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.pdf_label.selection_signal.connect(self.handle_selection)
        
        self.scroll_area.setWidget(self.pdf_label)
        layout.addWidget(self.scroll_area)

        self.btn_confirm = QPushButton("Confirmar Área")
        self.btn_confirm.setEnabled(False)
        self.btn_confirm.clicked.connect(self.accept)
        layout.addWidget(self.btn_confirm)

        self.load_pdf_image()

    def load_pdf_image(self):
        try:
            doc = fitz.open(self.pdf_path)
            page = doc[0] 
            self.page_rotation = page.rotation
            self.page_rect = page.rect
            
            zoom = 1.5 
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat) 
            
            img_format = QImage.Format.Format_RGB888
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, img_format)
            self.pdf_label.setPixmap(QPixmap.fromImage(img))
            self.scale_factor = zoom 
            doc.close()
        except Exception as e:
            print(f"Error: {str(e)}")

    def _map_visual_point_to_pdf(self, visual_x, visual_y):
        """
        Mapea coordenadas visuales a coordenadas PDF.
        RESTAURADA la lógica que funcionó para la posición (usando height para 270°).
        """
        rot = self.page_rotation % 360
        r = self.page_rect
        
        if rot == 0:
            return r.x0 + visual_x, r.y0 + visual_y
            
        elif rot == 90:
            return r.x0 + visual_y, r.x1 - visual_x
            
        elif rot == 180:
            return r.x1 - visual_x, r.y1 - visual_y
            
        elif rot == 270:
            # --- LÓGICA RESTAURADA ---
            # En el intento exitoso, usamos r.height (2004) para calcular X.
            # Visual Y (0..2004) se invierte para mapear a PDF X.
            pdf_x = r.height - visual_y
            
            # Ajuste de origen si existe
            if r.x0 != 0:
                 pdf_x = (r.x0 + r.height) - visual_y

            pdf_y = r.y0 + visual_x
            
            return pdf_x, pdf_y
            
        return r.x0 + visual_x, r.y0 + visual_y

    def handle_selection(self, x, y, w, h):
        vx, vy = x / self.scale_factor, y / self.scale_factor
        vw, vh = w / self.scale_factor, h / self.scale_factor
        
        # 1. Calcular puntos extremos
        p1_x, p1_y = self._map_visual_point_to_pdf(vx, vy)
        p2_x, p2_y = self._map_visual_point_to_pdf(vx + vw, vy + vh)
        
        # 2. Normalizar
        final_rect = fitz.Rect(p1_x, p1_y, p2_x, p2_y).normalize()
        real_x, real_y = final_rect.x0, final_rect.y0
        
        # 3. Intercambio de dimensiones
        rot = self.page_rotation % 360
        if rot == 90 or rot == 270:
            real_w = vh
            real_h = vw
        else:
            real_w = vw
            real_h = vh
            
        self.selected_geometry = (real_x, real_y, real_w, real_h)
        self.btn_confirm.setEnabled(True)
        self.btn_confirm.setText(f"Confirmar (X:{int(real_x)}, Y:{int(real_y)})")

    def get_geometry(self):
        return self.selected_geometry