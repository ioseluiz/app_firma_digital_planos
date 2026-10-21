"""
Sellado en segundo plano (la interfaz no se congela).

Medido con tools/benchmark.py en Windows: sellar cuesta ~40-60 ms por hoja (MuPDF
y Pillow trabajan en C), mientras que arrancar cada proceso hijo cuesta ~1 s. Por
eso el sellado es secuencial en este hilo y solo usa varios procesos en lotes
grandes, donde sí compensa (≈1.4× con 3 procesos a partir de ~120 hojas).
"""
import os
from concurrent.futures import ProcessPoolExecutor, as_completed

from PyQt6.QtCore import QThread, pyqtSignal

from app.utils.pdf_stamper import run_job

PARALLEL_MIN_PAGES = 120
PARALLEL_MAX_WORKERS = 3


def choose_workers(n_jobs, n_pages, cpu_count=None):
    """1 = secuencial. Varios procesos solo si el lote es grande."""
    cpus = cpu_count or os.cpu_count() or 1
    if n_pages < PARALLEL_MIN_PAGES or n_jobs < 2 or cpus < 3:
        return 1
    return max(1, min(n_jobs, cpus - 1, PARALLEL_MAX_WORKERS))


class SigningWorker(QThread):
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    job_finished = pyqtSignal(dict)            # resultado de pdf_stamper.run_job
    finished_signal = pyqtSignal(int, int, bool)   # correctos, fallidos, cancelado

    def __init__(self, jobs, max_workers=None):
        super().__init__()
        self.jobs = jobs
        n_pages = sum(len(j["args"]["placements"]) for j in jobs)
        self.max_workers = max_workers or choose_workers(len(jobs), n_pages)
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        total = len(self.jobs)
        ok = failed = done = 0
        self.status_updated.emit(f"Sellando {total} archivo{'s' if total != 1 else ''}…")
        try:
            executor = ProcessPoolExecutor(max_workers=self.max_workers) if self.max_workers > 1 else None
        except (OSError, NotImplementedError):
            executor = None

        def handle(result):
            nonlocal ok, failed, done
            done += 1
            ok += result.get("ok", False)
            failed += not result.get("ok", False)
            self.job_finished.emit(result)
            self.progress_updated.emit(int(done / total * 100))
            self.status_updated.emit(f"Sellados {done} de {total}")

        if executor is None:
            # Respaldo secuencial (1 núcleo o entornos sin multiprocessing)
            for job in self.jobs:
                if self._cancel:
                    break
                handle(run_job(job))
        else:
            with executor:
                futures = [executor.submit(run_job, job) for job in self.jobs]
                for fut in as_completed(futures):
                    if self._cancel:
                        for f in futures:
                            f.cancel()
                        break
                    try:
                        handle(fut.result())
                    except Exception as e:  # noqa: BLE001 - p. ej. proceso hijo caído
                        handle({"ok": False, "key": None, "src": None, "msg": str(e)})
        self.finished_signal.emit(ok, failed, self._cancel)
