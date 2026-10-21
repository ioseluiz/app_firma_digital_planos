import pytest

from app.utils import pdf_stamper
from app.workers.signing_worker import PARALLEL_MIN_PAGES, SigningWorker, choose_workers
from tests.conftest import ANSI_D, STAMP_H_MM, STAMP_W_MM


def test_choose_workers_policy():
    assert choose_workers(10, PARALLEL_MIN_PAGES - 1, cpu_count=20) == 1    # lote pequeño: secuencial
    assert choose_workers(1, 500, cpu_count=20) == 1                        # un solo archivo
    assert choose_workers(60, 180, cpu_count=20) == 3                       # lote grande: 3 procesos
    assert choose_workers(60, 180, cpu_count=2) == 1                        # pocos núcleos


def _jobs(pdf_factory, stamp_png, tmp_path, n):
    jobs = []
    for i in range(n):
        src = pdf_factory([ANSI_D])
        jobs.append({"key": src, "args": dict(
            src_path=src, out_path=str(tmp_path / f"out{i}.pdf"), placements=[(0, 1500, 900, 10.0)],
            stamp_png=stamp_png, stamp_w_mm=STAMP_W_MM, stamp_h_mm=STAMP_H_MM, hmac_key=b"k" * 32,
            owner_pw=pdf_stamper.generate_owner_password())})
    return jobs


@pytest.mark.parametrize("workers", [1, 2])
def test_worker_sequential_and_process_pool(qtbot, pdf_factory, stamp_png, tmp_path, workers):
    jobs = _jobs(pdf_factory, stamp_png, tmp_path, 3)
    w = SigningWorker(jobs, max_workers=workers)
    results = []
    w.job_finished.connect(results.append)
    with qtbot.waitSignal(w.finished_signal, timeout=60000) as blocker:
        w.start()
    assert blocker.args == [3, 0, False]
    assert all(r["ok"] for r in results) and len(results) == 3
