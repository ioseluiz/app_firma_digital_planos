# app/workers/loader_worker.py
"""Carga en segundo plano: expande carpetas, lee las hojas de cada PDF y detecta hojas ya selladas."""
import os

import pymupdf
from PyQt6.QtCore import QThread, pyqtSignal

from app.models.placement import DocumentEntry, PageInfo
from app.utils import seal_id


def expand_paths(raw_paths):
    """Archivos PDF de la lista, incluyendo los de carpetas (recursivo)."""
    found = []
    for path in raw_paths:
        path = os.path.normpath(path)
        if os.path.isdir(path):
            for root, _dirs, files in os.walk(path):
                found += [os.path.join(root, f) for f in sorted(files) if f.lower().endswith(".pdf")]
        elif path.lower().endswith(".pdf") and os.path.isfile(path):
            found.append(path)
    return list(dict.fromkeys(found))


def read_document(path, sealed_pages_by_hash):
    """DocumentEntry con sus hojas. `sealed_pages_by_hash(sha)` → páginas selladas según el registro."""
    sha = seal_id.sha256_file(path)
    with pymupdf.open(path) as doc:
        if doc.needs_pass:
            raise ValueError("el PDF está protegido con contraseña de apertura")
        locked = set()
        marker = seal_id.parse_keywords((doc.metadata or {}).get("keywords", ""))
        if marker:
            locked |= set(marker[1])
        locked |= set(sealed_pages_by_hash(sha))
        pages = [PageInfo(p.number, p.rect.width, p.rect.height, p.rotation, p.number in locked,
                          src_path=path, src_index=p.number)
                 for p in doc]
    if not pages:
        raise ValueError("el PDF no tiene hojas")
    return DocumentEntry(path, pages, sha256=sha)


class FileLoaderWorker(QThread):
    progress_updated = pyqtSignal(int)
    finished_signal = pyqtSignal(list, list)      # [DocumentEntry], [(path, error)]

    def __init__(self, raw_paths, sealed_index):
        """sealed_index: dict sha256 → [páginas] del registro de sellado (copiado del hilo principal)."""
        super().__init__()
        self.raw_paths = raw_paths
        self.sealed_index = sealed_index

    def run(self):
        paths = expand_paths(self.raw_paths)
        docs, errors = [], []
        total = len(paths)
        for i, path in enumerate(paths):
            try:
                docs.append(read_document(path, lambda sha: self.sealed_index.get(sha, [])))
            except Exception as e:  # noqa: BLE001
                errors.append((path, str(e)))
            self.progress_updated.emit(int((i + 1) / max(total, 1) * 100))
        self.finished_signal.emit(docs, errors)
