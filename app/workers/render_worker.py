# app/workers/render_worker.py
"""
Render de hojas en un hilo dedicado (PyMuPDF no es seguro entre hilos para el
mismo documento, así que todos los renders pasan por aquí).

- La hoja visible tiene prioridad; si llega una petición nueva, la anterior
  pendiente se descarta.
- Las miniaturas se procesan después, en orden.
"""
import collections
import threading

import pymupdf
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

MAX_RENDER_PIXELS = 36_000_000      # tope para planos grandes con mucho zoom
THUMB_SCALE_PX = 96                  # lado mayor de la miniatura
MAX_OPEN_DOCS = 4


class RenderWorker(QThread):
    page_rendered = pyqtSignal(int, str, int, float, QImage)     # token, path, page, scale, image
    thumb_rendered = pyqtSignal(str, int, QImage)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cond = threading.Condition()
        self._page_req = None
        self._thumbs = collections.deque()
        self._stop = False
        self._forget_paths = set()
        self._docs = collections.OrderedDict()

    def request_page(self, token, path, index, scale):
        with self._cond:
            self._page_req = (token, path, index, scale)
            self._cond.notify()

    def request_thumbs(self, keys):
        with self._cond:
            self._thumbs.extend(keys)
            self._cond.notify()

    def forget(self, path):
        with self._cond:
            self._thumbs = collections.deque(k for k in self._thumbs if k[0] != path)
            self._forget_paths.add(path)
            self._cond.notify()

    def stop(self):
        with self._cond:
            self._stop = True
            self._cond.notify()
        self.wait(3000)

    def _doc(self, path):
        doc = self._docs.pop(path, None)
        if doc is None:
            doc = pymupdf.open(path)
        self._docs[path] = doc
        while len(self._docs) > MAX_OPEN_DOCS:
            _, old = self._docs.popitem(last=False)
            old.close()
        return doc

    @staticmethod
    def _to_qimage(pix):
        fmt = QImage.Format.Format_RGB888
        return QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()

    def run(self):
        while True:
            with self._cond:
                while not (self._stop or self._page_req or self._thumbs or self._forget_paths):
                    self._cond.wait()
                if self._stop:
                    break
                forget, self._forget_paths = self._forget_paths, set()
                job = self._page_req
                self._page_req = None
                thumb = None if job else (self._thumbs.popleft() if self._thumbs else None)
            for path in forget:
                doc = self._docs.pop(path, None)
                if doc:
                    doc.close()
            try:
                if job:
                    token, path, index, scale = job
                    page = self._doc(path)[index]
                    area = page.rect.width * page.rect.height
                    scale = min(scale, (MAX_RENDER_PIXELS / max(area, 1)) ** 0.5)
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                    self.page_rendered.emit(token, path, index, scale, self._to_qimage(pix))
                elif thumb:
                    path, index = thumb
                    page = self._doc(path)[index]
                    scale = THUMB_SCALE_PX / max(page.rect.width, page.rect.height)
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                    self.thumb_rendered.emit(path, index, self._to_qimage(pix))
            except Exception as e:  # noqa: BLE001 - un PDF dañado no debe tumbar el hilo
                print(f"Render: error en {job or thumb}: {e}")
        for doc in self._docs.values():
            doc.close()
        self._docs.clear()
