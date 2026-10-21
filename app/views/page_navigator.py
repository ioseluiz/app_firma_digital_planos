"""Navegador Archivo ▸ Hojas con miniaturas, estado de sellado y acciones para armar el documento."""
import os

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QAbstractItemView, QMenu, QTreeWidget, QTreeWidgetItem

from app.models.placement import PROFILE_PLAN, PROFILE_REPORT
from app.views.icons import icon

ROLE_KEY = Qt.ItemDataRole.UserRole          # (path, page_index) o (path, None)
ROLE_SRC = Qt.ItemDataRole.UserRole + 1      # (pdf de origen, página de origen)

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
    # Armar el documento final
    delete_pages_requested = pyqtSignal(str, list)          # path, [índices]
    insert_pages_requested = pyqtSignal(str, int)           # path, posición
    move_page_requested = pyqtSignal(str, int, int)         # path, índice, desplazamiento

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
        self._thumbs = {}    # (pdf origen, página origen) -> QIcon
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
        self._add_pages(top, doc)
        top.setExpanded(True)
        self.update_file_label(doc, 0)

    def _add_pages(self, top, doc):
        for page in doc.pages:
            src = doc.source(page)
            child = QTreeWidgetItem([self._page_text(doc, page, src), ""])
            child.setData(0, ROLE_KEY, (doc.path, page.index))
            child.setData(0, ROLE_SRC, src)
            if src != (doc.path, page.index):
                child.setToolTip(0, f"Origen: {src[0]}\nHoja original {src[1] + 1}")
            child.setIcon(0, self._thumbs.get(src) or self._placeholder_thumb())
            child.setSizeHint(0, QSize(0, THUMB.height() + 6))
            top.addChild(child)
            self._pages[(doc.path, page.index)] = child

    def rebuild_document(self, doc):
        """Vuelve a crear las hojas de un archivo tras borrar, insertar o reordenar."""
        top = self._files.get(doc.path)
        if top is None:
            return
        self.blockSignals(True)
        try:
            for key in [k for k in self._pages if k[0] == doc.path]:
                del self._pages[key]
            top.takeChildren()
            self._add_pages(top, doc)
        finally:
            self.blockSignals(False)

    def missing_thumbnails(self, sources):
        return [s for s in dict.fromkeys(sources) if s not in self._thumbs]

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
    def _page_text(doc, page, src):
        text = f"Hoja {page.index + 1} · {page.format_name}"
        if src != (doc.path, page.index):
            origin = "original" if src[0] == doc.path else os.path.splitext(os.path.basename(src[0]))[0]
            text += f"\n↳ {origin} · h.{src[1] + 1}"
        return text

    def _placeholder_thumb(self):
        pm = QPixmap(THUMB)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setPen(QColor(self._tokens["border_strong"]))
        p.setBrush(QColor(self._tokens["surface_alt"]))
        p.drawRect(8, 2, THUMB.width() - 17, THUMB.height() - 5)
        p.end()
        return QIcon(pm)

    def set_thumbnail(self, src_path, src_index, qimage):
        """Miniatura de una hoja de origen; se aplica a todas las hojas que la usan."""
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
        ic = QIcon(pm)
        self._thumbs[(src_path, src_index)] = ic
        for item in self._pages.values():
            if tuple(item.data(0, ROLE_SRC)) == (src_path, src_index):
                item.setIcon(0, ic)

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
        edited = " · editado" if doc.is_modified() else ""
        top.setText(0, f"{doc.name}\n{kind} · {sealed_count}/{n} con sello{edited}")
        top.setToolTip(0, doc.path + ("\nEl documento final tendrá hojas borradas, reordenadas o insertadas."
                                      if edited else ""))

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
        if idx is not None:
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
        path, idx = item.data(0, ROLE_KEY)
        menu = QMenu(self)
        n_pages = len([k for k in self._pages if k[0] == path])
        if idx is not None:
            # Hojas del mismo archivo seleccionadas (para borrar varias a la vez)
            sel = sorted(i for p, i in self.selected_pages() if p == path)
            if idx not in sel:
                sel = [idx]
            label = (f"Eliminar {len(sel)} hojas del documento" if len(sel) > 1
                     else "Eliminar esta hoja del documento")
            act = menu.addAction(label, lambda: self.delete_pages_requested.emit(path, sel))
            act.setEnabled(len(sel) < n_pages)
            menu.addAction("Insertar hojas de otro PDF antes…",
                           lambda: self.insert_pages_requested.emit(path, idx))
            menu.addAction("Insertar hojas de otro PDF después…",
                           lambda: self.insert_pages_requested.emit(path, idx + 1))
            up = menu.addAction("Mover hoja arriba  (Alt+↑)", lambda: self.move_page_requested.emit(path, idx, -1))
            down = menu.addAction("Mover hoja abajo  (Alt+↓)", lambda: self.move_page_requested.emit(path, idx, 1))
            up.setEnabled(idx > 0)
            down.setEnabled(idx < n_pages - 1)
            menu.addSeparator()
        else:
            menu.addAction("Añadir hojas de otro PDF al final…",
                           lambda: self.insert_pages_requested.emit(path, n_pages))
            menu.addSeparator()
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

    def keyPressEvent(self, event):
        key = self.current_key()
        if key and key[1] is not None and event.modifiers() & Qt.KeyboardModifier.AltModifier \
                and event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            self.move_page_requested.emit(key[0], key[1], -1 if event.key() == Qt.Key.Key_Up else 1)
            return
        super().keyPressEvent(event)

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
