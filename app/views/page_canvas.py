"""
Lienzo de una hoja: la página renderizada y su (único) sello, que se puede mover
y rotar libremente pero nunca escalar (siempre a tamaño real).

Coordenadas de escena = coordenadas visuales de la hoja en puntos PDF.
"""
import math

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QBrush, QColor, QFont, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsItem, QGraphicsObject, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene,
    QGraphicsView, QMenu,
)

from app.utils import geometry

HANDLE_RADIUS_PX = 7      # tamaño del asa en pantalla (independiente del zoom)
HANDLE_OFFSET_PX = 26     # distancia del asa al borde superior del sello
MIN_ZOOM, MAX_ZOOM = 0.03, 12.0


class StampItem(QGraphicsObject):
    """Sello movible y rotable. Su tamaño es fijo (escala real)."""

    live_changed = pyqtSignal(float, float, float)        # cx, cy, rot mientras se arrastra
    committed = pyqtSignal(float, float, float)           # cx, cy, rot al soltar

    def __init__(self, pixmap, w_pt, stamp_h_pt, strip_h_pt, page_w, page_h, accent):
        super().__init__()
        self._pixmap = pixmap
        self._w, self._stamp_h, self._strip_h = w_pt, stamp_h_pt, strip_h_pt
        self._h = stamp_h_pt + strip_h_pt
        self._page_w, self._page_h = page_w, page_h
        self._accent = QColor(accent)
        self._view_scale = 1.0
        self._rotating = False
        self._press_state = None
        self._hover = False
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
                      | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setZValue(10)

    # ------------------------------------------------------------ geometry
    def set_view_scale(self, s):
        if abs(s - self._view_scale) > 1e-9:
            self.prepareGeometryChange()
            self._view_scale = s

    def _px(self, v):
        return v / max(self._view_scale, 1e-6)

    def _body(self):
        return QRectF(-self._w / 2, -self._h / 2, self._w, self._h)

    def _handle_center(self):
        return QPointF(0, -self._h / 2 - self._px(HANDLE_OFFSET_PX))

    def boundingRect(self):
        r = self._px(HANDLE_RADIUS_PX + 2)
        hc = self._handle_center()
        return self._body().united(QRectF(hc.x() - r, hc.y() - r, 2 * r, 2 * r)).adjusted(-r, -r, r, r)

    def shape(self):
        from PyQt6.QtGui import QPainterPath
        path = QPainterPath()
        path.addRect(self._body())
        if self.isSelected():
            r = self._px(HANDLE_RADIUS_PX + 3)
            path.addEllipse(self._handle_center(), r, r)
        return path

    def _on_handle(self, pos):
        if not self.isSelected():
            return False
        d = pos - self._handle_center()
        return math.hypot(d.x(), d.y()) <= self._px(HANDLE_RADIUS_PX + 4)

    # ------------------------------------------------------------ painting
    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        stamp_rect = QRectF(-self._w / 2, -self._h / 2, self._w, self._stamp_h)
        painter.drawPixmap(stamp_rect, self._pixmap, QRectF(self._pixmap.rect()))

        # Franja del ID (se genera al sellar)
        strip = QRectF(-self._w / 2, -self._h / 2 + self._stamp_h, self._w, self._strip_h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 150))
        painter.drawRect(strip)
        font = QFont("Segoe UI")
        font.setPointSizeF(max(0.5, self._strip_h * 0.45))
        painter.setFont(font)
        painter.setPen(QColor(90, 90, 90))
        painter.drawText(strip, Qt.AlignmentFlag.AlignCenter, "Proyecto · Hoja n/N · fecha · ID (al sellar)")

        if self.isSelected() or self._hover:
            pen = QPen(self._accent, self._px(1.5))
            pen.setStyle(Qt.PenStyle.DashLine if not self.isSelected() else Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._body())
        if self.isSelected():
            hc = self._handle_center()
            painter.setPen(QPen(self._accent, self._px(1.5)))
            painter.drawLine(QPointF(0, -self._h / 2), hc)
            painter.setBrush(QColor("white"))
            r = self._px(HANDLE_RADIUS_PX)
            painter.drawEllipse(hc, r, r)
            painter.setBrush(self._accent)
            painter.drawEllipse(hc, r * 0.45, r * 0.45)

    # ------------------------------------------------------------ state
    def state(self):
        return self.pos().x(), self.pos().y(), self.rotation()

    def set_state(self, cx, cy, rot):
        self.setRotation(rot)
        self.setPos(cx, cy)

    def _clamped(self, x, y, rot):
        try:
            return QPointF(*geometry.clamp_center(x, y, self._w, self._h, rot, self._page_w, self._page_h))
        except ValueError:
            return QPointF(x, y)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            return self._clamped(value.x(), value.y(), self.rotation())
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and not self._rotating:
            self.live_changed.emit(*self.state())
        return super().itemChange(change, value)

    # ------------------------------------------------------------ mouse
    def hoverEnterEvent(self, event):
        self._hover = True
        self.update()

    def hoverMoveEvent(self, event):
        self.setCursor(Qt.CursorShape.CrossCursor if self._on_handle(event.pos())
                       else Qt.CursorShape.SizeAllCursor)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        self._press_state = self.state()
        if event.button() == Qt.MouseButton.LeftButton and self._on_handle(event.pos()):
            self._rotating = True
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._rotating:
            v = event.scenePos() - self.pos()
            angle = math.degrees(math.atan2(v.y(), v.x())) + 90.0
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                angle = round(angle / 15.0) * 15.0
            angle = geometry.normalize_angle(angle)
            self.setRotation(angle)
            self.setPos(self._clamped(self.pos().x(), self.pos().y(), angle))
            self.live_changed.emit(*self.state())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._rotating = False
        super().mouseReleaseEvent(event)
        if self._press_state is not None and self.state() != self._press_state:
            self.committed.emit(*self.state())
        self._press_state = None


class PageCanvas(QGraphicsView):
    # Ediciones confirmadas (el controlador las convierte en comandos deshacer/rehacer)
    stamp_committed = pyqtSignal(float, float, float)
    stamp_live = pyqtSignal(float, float, float)
    place_requested = pyqtSignal(float, float)
    remove_requested = pyqtSignal()
    nudge_requested = pyqtSignal(float, float)            # dx, dy en pt
    rotate_by_requested = pyqtSignal(float)                # grados
    render_requested = pyqtSignal(float)                   # escala de render deseada (px por pt)
    cursor_moved = pyqtSignal(object)                      # (x_pt, y_pt) o None
    zoom_changed = pyqtSignal(float)
    files_dropped = pyqtSignal(list)

    def __init__(self, tokens, parent=None):
        super().__init__(parent)
        self._tokens = tokens
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._page = None
        self._locked = False
        self._banner = ""
        self._page_item = None
        self._shadow_item = None
        self._stamp_item = None
        self._stamp_spec = None       # (pixmap, w_pt, stamp_h_pt, strip_h_pt)
        self._image_scale = 0.0
        self._space_down = False
        self._panning_from_middle = False
        self._fit_mode = True

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(160)
        self._render_timer.timeout.connect(self._request_render)

    # ------------------------------------------------------------ public API
    def set_tokens(self, tokens):
        self._tokens = tokens
        if self._shadow_item:
            self._shadow_item.setBrush(QColor(tokens["page_shadow"]))
        if self._stamp_item:
            self._stamp_item._accent = QColor(tokens["accent"])
        self.viewport().update()

    def set_stamp_spec(self, pixmap, w_pt, stamp_h_pt, strip_h_pt):
        self._stamp_spec = (pixmap, w_pt, stamp_h_pt, strip_h_pt)
        if self._page is not None:
            placement = self.current_state()
            self._rebuild_stamp(placement)

    def show_page(self, page, placement, locked, banner=None):
        """Muestra una hoja (PageInfo) con su colocación (o None).

        locked: la hoja no admite cambios; banner: texto del aviso superior.
        """
        same_size = (self._page is not None and page is not None
                     and (self._page.width, self._page.height) == (page.width, page.height))
        self.scene().clear()
        self._page_item = self._shadow_item = self._stamp_item = None
        self._image_scale = 0.0
        self._page, self._locked = page, locked
        self._banner = banner or "Hoja ya sellada por DigitalSealer · no admite otro sello"
        if page is None:
            self.scene().setSceneRect(QRectF())
            self.viewport().update()
            return
        margin = max(page.width, page.height) * 0.08
        self.scene().setSceneRect(QRectF(-margin, -margin, page.width + 2 * margin, page.height + 2 * margin))
        shadow_off = max(page.width, page.height) * 0.0025
        self._shadow_item = QGraphicsRectItem(shadow_off, shadow_off, page.width, page.height)
        self._shadow_item.setBrush(QColor(self._tokens["page_shadow"]))
        self._shadow_item.setPen(QPen(Qt.PenStyle.NoPen))
        self.scene().addItem(self._shadow_item)
        white = QGraphicsRectItem(0, 0, page.width, page.height)
        white.setBrush(QBrush(QColor("white")))
        white.setPen(QPen(Qt.PenStyle.NoPen))
        self.scene().addItem(white)
        self._rebuild_stamp(placement)
        if self._fit_mode or not same_size:
            self.fit_page()
        else:
            self._schedule_render()
        self.viewport().update()

    def set_page_image(self, qimage, scale):
        """Imagen renderizada de la hoja actual a `scale` px por pt."""
        if self._page is None:
            return
        if self._page_item is not None:
            self.scene().removeItem(self._page_item)
        item = QGraphicsPixmapItem(QPixmap.fromImage(qimage))
        item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        item.setScale(1.0 / scale)
        item.setZValue(1)
        self.scene().addItem(item)
        self._page_item = item
        self._image_scale = scale

    def update_placement(self, placement):
        """Sincroniza el sello con el modelo (tras deshacer, spinbox, etc.)."""
        if self._page is None:
            return
        if placement is None:
            if self._stamp_item is not None:
                self.scene().removeItem(self._stamp_item)
                self._stamp_item = None
            return
        if self._stamp_item is None:
            self._rebuild_stamp(placement)
        else:
            self._stamp_item.blockSignals(True)
            self._stamp_item.set_state(placement.cx, placement.cy, placement.rotation)
            self._stamp_item.blockSignals(False)
        self.viewport().update()

    def current_state(self):
        return self._stamp_item.state() if self._stamp_item else None

    def select_stamp(self):
        if self._stamp_item:
            self.scene().clearSelection()
            self._stamp_item.setSelected(True)
            self.centerOn(self._stamp_item)

    def zoom_factor(self):
        return self.transform().m11()

    def fit_page(self):
        if self._page is None:
            return
        self._fit_mode = True
        pad = max(self._page.width, self._page.height) * 0.03
        self.fitInView(QRectF(-pad, -pad, self._page.width + 2 * pad, self._page.height + 2 * pad),
                       Qt.AspectRatioMode.KeepAspectRatio)
        self._after_zoom()

    def zoom_by(self, factor, anchor_under_mouse=False):
        current = self.zoom_factor()
        factor = max(MIN_ZOOM / current, min(MAX_ZOOM / current, factor))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse if anchor_under_mouse
                                     else QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.scale(factor, factor)
        self._fit_mode = False
        self._after_zoom()

    def set_zoom(self, z):
        self.zoom_by(z / self.zoom_factor())

    # ------------------------------------------------------------ internals
    def _rebuild_stamp(self, placement):
        if self._stamp_item is not None:
            self.scene().removeItem(self._stamp_item)
            self._stamp_item = None
        if placement is None or self._stamp_spec is None or self._page is None:
            return
        pixmap, w, sh, strip = self._stamp_spec
        item = StampItem(pixmap, w, sh, strip, self._page.width, self._page.height, self._tokens["accent"])
        if isinstance(placement, tuple):
            item.set_state(*placement)
        else:
            item.set_state(placement.cx, placement.cy, placement.rotation)
        item.set_view_scale(self.zoom_factor())
        locked = self._locked
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not locked)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, not locked)
        item.live_changed.connect(self.stamp_live)
        item.committed.connect(self.stamp_committed)
        self.scene().addItem(item)
        self._stamp_item = item

    def _after_zoom(self):
        if self._stamp_item:
            self._stamp_item.set_view_scale(self.zoom_factor())
        self.zoom_changed.emit(self.zoom_factor())
        self._schedule_render()

    def _schedule_render(self):
        self._render_timer.start()

    def _request_render(self):
        if self._page is None:
            return
        wanted = self.zoom_factor() * self.devicePixelRatioF()
        # Re-renderizar solo si la resolución actual se queda corta o sobra mucho
        if self._image_scale <= 0 or wanted > self._image_scale * 1.15 or wanted < self._image_scale * 0.5:
            self.render_requested.emit(wanted)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit_mode:
            self.fit_page()

    # ------------------------------------------------------------ input
    def wheelEvent(self, event):
        if self._page is None:
            return
        delta = event.angleDelta().y()
        if not delta:
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and self._stamp_item and not self._locked:
            item = self.itemAt(event.position().toPoint())
            if item is self._stamp_item:
                self.rotate_by_requested.emit(1.0 if delta > 0 else -1.0)
                return
        self.zoom_by(1.0015 ** delta, anchor_under_mouse=True)

    def keyPressEvent(self, event):
        key, mods = event.key(), event.modifiers()
        if key == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_down = True
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            return
        if self._stamp_item and not self._locked:
            step = geometry.mm_to_pt(10.0 if mods & Qt.KeyboardModifier.ShiftModifier else 1.0)
            moves = {Qt.Key.Key_Left: (-step, 0), Qt.Key.Key_Right: (step, 0),
                     Qt.Key.Key_Up: (0, -step), Qt.Key.Key_Down: (0, step)}
            if key in moves:
                self.nudge_requested.emit(*moves[key])
                return
            if key == Qt.Key.Key_R:
                self.rotate_by_requested.emit(-90.0 if mods & Qt.KeyboardModifier.ShiftModifier else 90.0)
                return
            if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self.remove_requested.emit()
                return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_down = False
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            return
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            # Pan con el botón central: simular arrastre con la mano
            self._panning_from_middle = True
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            from PyQt6.QtGui import QMouseEvent
            fake = QMouseEvent(event.type(), event.position(), event.globalPosition(),
                               Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, event.modifiers())
            super().mousePressEvent(fake)
            return
        if self._space_down:
            super().mousePressEvent(event)
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning_from_middle and event.button() == Qt.MouseButton.MiddleButton:
            from PyQt6.QtGui import QMouseEvent
            fake = QMouseEvent(event.type(), event.position(), event.globalPosition(),
                               Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, event.modifiers())
            super().mouseReleaseEvent(fake)
            self._panning_from_middle = False
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if self._page is None:
            return
        p = self.mapToScene(event.position().toPoint())
        inside = 0 <= p.x() <= self._page.width and 0 <= p.y() <= self._page.height
        self.cursor_moved.emit((p.x(), p.y()) if inside else None)

    def leaveEvent(self, event):
        self.cursor_moved.emit(None)
        super().leaveEvent(event)

    def contextMenuEvent(self, event):
        if self._page is None:
            return
        p = self.mapToScene(event.pos())
        menu = QMenu(self)
        if self._locked:
            act = QAction(self._banner, menu)
            act.setEnabled(False)
            menu.addAction(act)
        else:
            text = "Mover el sello aquí" if self._stamp_item else "Colocar sello aquí"
            menu.addAction(text, lambda: self.place_requested.emit(p.x(), p.y()))
            if self._stamp_item:
                menu.addSeparator()
                menu.addAction("Rotar 90° a la derecha  (R)", lambda: self.rotate_by_requested.emit(90.0))
                menu.addAction("Rotar 90° a la izquierda  (Shift+R)", lambda: self.rotate_by_requested.emit(-90.0))
                menu.addSeparator()
                menu.addAction("Quitar sello de esta hoja  (Supr)", self.remove_requested.emit)
        menu.exec(event.globalPos())

    # ------------------------------------------------------------ drag & drop
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            self.files_dropped.emit([u.toLocalFile() for u in urls])
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    # ------------------------------------------------------------ overlays
    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        painter.save()
        painter.resetTransform()
        vp = self.viewport().rect()
        t = self._tokens
        if self._page is None:
            painter.setPen(QColor(t["text_muted"]))
            f = QFont("Segoe UI")
            f.setPointSize(13)
            painter.setFont(f)
            painter.drawText(vp, Qt.AlignmentFlag.AlignCenter,
                             "Arrastra aquí planos o reportes en PDF\n(o usa «Abrir PDFs»)")
        elif self._locked:
            f = QFont("Segoe UI")
            f.setPointSize(10)
            f.setBold(True)
            painter.setFont(f)
            text = self._banner
            w = painter.fontMetrics().horizontalAdvance(text) + 28
            box = QRectF((vp.width() - w) / 2, 12, w, 30)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t["warning"]))
            painter.drawRoundedRect(box, 15, 15)
            painter.setPen(QColor("white"))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()
