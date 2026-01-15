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
    def __init__(self, pdf_path, initial_coords=None):
        super().__init__()
        self.setWindowTitle("Editor de Posición - Ajuste Fino")
        self.resize(1000, 800)
        self.pdf_path = pdf_path
        
        # Coordenadas iniciales (x, y, w, h) reales del PDF
        self.selected_geometry = initial_coords 
        
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

            # --- SI HAY COORDENADAS PREVIAS, DIBUJARLAS ---
            if self.selected_geometry:
                rx, ry, rw, rh = self.selected_geometry
                vx, vy, vw, vh = self._map_pdf_rect_to_visual(rx, ry, rw, rh)
                
                # Establecer el rectángulo visual
                self.pdf_label.current_rect = QRect(int(vx), int(vy), int(vw), int(vh))
                self.pdf_label.update()
                
                # Activar botón
                self.btn_confirm.setEnabled(True)
                self.btn_confirm.setText(f"Confirmar (X:{int(rx)}, Y:{int(ry)})")

        except Exception as e:
            print(f"Error: {str(e)}")

    def _map_visual_point_to_pdf(self, visual_x, visual_y):
        """Mapea coordenadas visuales a coordenadas PDF (Lógica probada)."""
        rot = self.page_rotation % 360
        r = self.page_rect
        
        if rot == 0:
            return r.x0 + visual_x, r.y0 + visual_y
        elif rot == 90:
            return r.x0 + visual_y, r.x1 - visual_x
        elif rot == 180:
            return r.x1 - visual_x, r.y1 - visual_y
        elif rot == 270:
            # Lógica para planos verticales (Landscape en PDF)
            pdf_x = r.height - visual_y
            if r.x0 != 0: pdf_x = (r.x0 + r.height) - visual_y
            pdf_y = r.y0 + visual_x
            return pdf_x, pdf_y
            
        return r.x0 + visual_x, r.y0 + visual_y

    def _map_pdf_rect_to_visual(self, x, y, w, h):
        """Convierte coordenadas PDF a visuales para pintar el recuadro inicial."""
        rot = self.page_rotation % 360
        r = self.page_rect
        
        # Invertir la lógica de _map_visual_point_to_pdf
        if rot == 0:
            vx = x - r.x0
            vy = y - r.y0
            vw, vh = w, h
        elif rot == 90:
            # En 90: PDF X viene de Visual Y. PDF Y viene de Inverted Visual X
            vx = r.x1 - y
            vy = x - r.x0
            vw, vh = h, w # Dimensiones invertidas
        elif rot == 180:
            vx = r.x1 - x
            vy = r.y1 - y
            vw, vh = w, h
        elif rot == 270:
            # Inverso de la lógica 270
            offset_x = (r.x0 + r.height) if r.x0 != 0 else r.height
            vy = offset_x - x
            vx = y - r.y0
            vw, vh = h, w # Dimensiones invertidas
        else:
            vx, vy, vw, vh = x, y, w, h

        # Aplicar escala (Zoom)
        return (vx * self.scale_factor, vy * self.scale_factor, 
                vw * self.scale_factor, vh * self.scale_factor)

    def handle_selection(self, x, y, w, h):
        vx, vy = x / self.scale_factor, y / self.scale_factor
        vw, vh = w / self.scale_factor, h / self.scale_factor
        
        # 1. Calcular puntos extremos
        p1_x, p1_y = self._map_visual_point_to_pdf(vx, vy)
        p2_x, p2_y = self._map_visual_point_to_pdf(vx + vw, vy + vh)
        
        # 2. Normalizar
        final_rect = fitz.Rect(p1_x, p1_y, p2_x, p2_y).normalize()
        real_x, real_y = final_rect.x0, final_rect.y0
        
        # 3. Intercambio de dimensiones si hay rotación
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