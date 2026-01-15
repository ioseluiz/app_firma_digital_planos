# app/workers/loader_worker.py
from PyQt6.QtCore import QThread, pyqtSignal
import os

class FileLoaderWorker(QThread):
    progress_updated = pyqtSignal(int)
    finished_signal = pyqtSignal(list) # Retorna la lista filtrada de PDFs

    def __init__(self, raw_paths):
        super().__init__()
        self.raw_paths = raw_paths

    def run(self):
        valid_pdfs = []
        total = len(self.raw_paths)
        
        if total == 0:
            self.finished_signal.emit([])
            return

        for i, path in enumerate(self.raw_paths):
            # Normalizar ruta (útil para Windows)
            clean_path = os.path.normpath(path)
            
            # Verificación rápida
            if clean_path.lower().endswith('.pdf') and os.path.exists(clean_path):
                valid_pdfs.append(clean_path)
            
            # Actualizamos la barra cada 10 archivos o al final (para no saturar eventos)
            if i % 10 == 0 or i == total - 1:
                percent = int(((i + 1) / total) * 100)
                self.progress_updated.emit(percent)

        self.finished_signal.emit(valid_pdfs)