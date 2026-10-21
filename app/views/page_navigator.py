"""Navegador Archivo ▸ Hojas con miniaturas y estado de sellado de cada hoja."""
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QAbstractItemView, QMenu, QTreeWidget, QTreeWidgetItem

from app.models.placement import PROFILE_PLAN, PROFILE_REPORT
from app.views.icons import icon

ROLE_KEY = Qt.ItemDataRole.UserRole          # (path, page_index) o (path, None)

STATUS_NONE = "none"          # sin sello
STATUS_PLACED = "placed"      # sello colocado (posición inicial)
STATUS_MANUAL = "manual"      # sello ajustado a mano
STATUS_LOCKED = "locked"      # ya sellada antes: bloqueada
STATUS_DONE = "done"          # sellada en esta sesión
STATUS_ERROR = "error"

THUMB = QSize(46, 46)


class PageNavigator(QTreeWidget):
    page_selected = pyqtSignal(str, int)
    profile_change_requested = pyqtSignal(str, str)        # path, profile
    seal_all_requested = pyqtSignal(str)
    clear_all_requested = pyqtSignal(str)
    remove_file_requested = pyqtSignal(str)
    files_dropped = pyqtSignal(list)

    def __init__(self, tokens, parent=None):
        super().__init__(parent)
        self._tokens = tokens
        self.setColumnCount(2)
        self.setHeaderHidden(True)
        self.setIconSize(THUMB)
        self.setIndentation(14)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setUniformRowHeights(False)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0, self.header().ResizeMode.Stretch)
        self.header().setSectionResizeMode(1, self.header().ResizeMode.Fixed)
        self.header().resizeSection(1, 30)
        self._files = {}     # path -> QTreeWidgetItem
        self._pages = {}     # (path, idx) -> QTreeWidgetItem
        self.currentItemChanged.connect(self._on_current_changed)

    def set_tokens(self, tokens):
        self._tokens = tokens
        for key, item in self._pages.items():
            self._apply_status_icon(item, item.data(1, ROLE_KEY) or STATUS_NONE)
        for item in self._files.values():
            item.setIcon(0, icon("file", tokens["text_muted"], 18))

    # ------------------------------------------------------------ build
    def add_document(self, doc):
        t = self._tokens
        top = QTreeWidgetItem([doc.name, ""])
        top.setData(0, ROLE_KEY, (doc.path, None))
        top.setToolTip(0, doc.path)
        top.setIcon(0, icon("file", t["text_muted"], 18))
        f = top.font(0)
        f.setBold(True)
        top.setFont(0, f)
        self.addTopLevelItem(top)
        self._files[doc.path] = top
        for page in doc.pages:
            child = QTreeWidgetItem([self._page_text(page), ""])
            child.setData(0, ROLE_KEY, (doc.path, page.index))
            child.setIcon(0, self._placeholder_thumb())
            child.setSizeHint(0, QSize(0, THUMB.height() + 6))
            top.addChild(child)
            self._pages[(doc.path, page.index)] = child
        top.setExpanded(True)
        self.update_file_label(doc, 0)

    def remove_document(self, path):
        top = self._files.pop(path, None)
        if top is None:
            return
        for key in [k for k in self._pages if k[0] == path]:
            del self._pages[key]
        self.takeTopLevelItem(self.indexOfTopLevelItem(top))

    def clear_all(self):
        self.clear()
        self._files.clear()
        self._pages.clear()

    @staticmethod
    def _page_text(page):
        return f"Hoja {page.index + 1}\n{page.format_name}"

    def _placeholder_thumb(self):
        pm = QPixmap(THUMB)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setPen(QColor(self._tokens["border_strong"]))
        p.setBrush(QColor(self._tokens["surface_alt"]))
        p.drawRect(8, 2, THUMB.width() - 17, THUMB.height() - 5)
        p.end()
        return QIcon(pm)

    def set_thumbnail(self, path, index, qimage):
        item = self._pages.get((path, index))
        if item is None:
            return
        pm = QPixmap(THUMB)
        pm.fill(Qt.GlobalColor.transparent)
        img = QPixmap.fromImage(qimage).scaled(THUMB.width() - 4, THUMB.height() - 4,
                                               Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation)
        p = QPainter(pm)
        x, y = (THUMB.width() - img.width()) // 2, (THUMB.height() - img.height()) // 2
        p.drawPixmap(x, y, img)
        p.setPen(QColor(self._tokens["border_strong"]))
        p.drawRect(x, y, img.width() - 1, img.height() - 1)
        p.end()
        item.setIcon(0, QIcon(pm))

    def thumbnails_needed(self):
        return list(self._pages.keys())

    # ------------------------------------------------------------ status
    def set_page_status(self, path, index, status, tooltip=""):
        item = self._pages.get((path, index))
        if item is None:
            return
        item.setData(1, ROLE_KEY, status)
        self._apply_status_icon(item, status)
        tips = {
            STATUS_NONE: "Sin sello",
            STATUS_PLACED: "Sello colocado (posición inicial)",
            STATUS_MANUAL: "Sello ajustado manualmente",
            STATUS_LOCKED: "Hoja ya sellada: bloqueada",
            STATUS_DONE: "Sellada",
            STATUS_ERROR: "Error al sellar",
        }
        item.setToolTip(1, tooltip or tips.get(status, ""))
        item.setToolTip(0, tooltip or tips.get(status, ""))

    def _apply_status_icon(self, item, status):
        t = self._tokens
        spec = {
            STATUS_NONE: ("dot", t["border_strong"]),
            STATUS_PLACED: ("seal", t["accent"]),
            STATUS_MANUAL: ("seal", t["success"]),
            STATUS_LOCKED: ("lock", t["warning"]),
            STATUS_DONE: ("check", t["success"]),
            STATUS_ERROR: ("error", t["danger"]),
        }.get(status, ("dot", t["border_strong"]))
        item.setIcon(1, icon(spec[0], spec[1], 18))

    def update_file_label(self, doc, sealed_count):
        top = self._files.get(doc.path)
        if top is None:
            return
        kind = "Reporte" if doc.profile == PROFILE_REPORT else "Plano"
        n = len(doc.pages)
        top.setText(0, f"{doc.name}\n{kind} · {sealed_count}/{n} hoja{'s' if n != 1 else ''} con sello")

    # ------------------------------------------------------------ selection
    def select_page(self, path, index):
        item = self._pages.get((path, index))
        if item:
            self.setCurrentItem(item)

    def current_key(self):
        item = self.currentItem()
        return item.data(0, ROLE_KEY) if item else None

    def selected_pages(self):
        """Hojas seleccionadas (expandiendo archivos seleccionados a todas sus hojas)."""
        keys = []
        for item in self.selectedItems():
            path, idx = item.data(0, ROLE_KEY)
            if idx is None:
                keys += [k for k in self._pages if k[0] == path]
            else:
                keys.append((path, idx))
        return list(dict.fromkeys(keys))

    def _on_current_changed(self, current, _previous):
        if current is None:
            return
        path, idx = current.data(0, ROLE_KEY)
        if idx is None:
            if current.childCount():
                # Al elegir un archivo, mostrar su primera hoja
                return
            return
        self.page_selected.emit(path, idx)

    def page_order(self):
        """Todas las hojas en el orden mostrado."""
        order = []
        for i in range(self.topLevelItemCount()):
            top = self.topLevelItem(i)
            for j in range(top.childCount()):
                order.append(tuple(top.child(j).data(0, ROLE_KEY)))
        return order

    # ------------------------------------------------------------ menus / dnd
    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if item is None:
            return
        path, _idx = item.data(0, ROLE_KEY)
        menu = QMenu(self)
        prof = menu.addMenu("Tipo de documento")
        prof.addAction("Plano  (sello en todas las hojas)",
                       lambda: self.profile_change_requested.emit(path, PROFILE_PLAN))
        prof.addAction("Reporte  (sello solo en la última hoja)",
                       lambda: self.profile_change_requested.emit(path, PROFILE_REPORT))
        menu.addAction("Poner sello en todas las hojas", lambda: self.seal_all_requested.emit(path))
        menu.addAction("Quitar todos los sellos del archivo", lambda: self.clear_all_requested.emit(path))
        menu.addSeparator()
        menu.addAction("Quitar archivo de la lista", lambda: self.remove_file_requested.emit(path))
        menu.exec(event.globalPos())

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            self.files_dropped.emit([u.toLocalFile() for u in urls])
            event.acceptProposedAction()
