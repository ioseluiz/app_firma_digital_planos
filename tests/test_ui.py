"""Prueba de extremo a extremo de la interfaz (Qt offscreen), sin tocar el AppData real."""
import os

import pymupdf
import pytest
from PyQt6.QtWidgets import QMessageBox

from app.models.placement import PROFILE_REPORT
from app.utils import geometry, seal_id
from app.views import page_navigator as nav
from tests.conftest import ANSI_D, LETTER, STAMP_H_MM, STAMP_W_MM, make_pdf


@pytest.fixture
def ctrl(qtbot, tmp_path, monkeypatch, stamp_png):
    data_dir = tmp_path / "appdata"
    data_dir.mkdir()
    monkeypatch.setattr("app.models.database.get_app_data_path", lambda: str(data_dir))
    monkeypatch.setattr("app.controllers.main_controller.get_app_data_path", lambda: str(data_dir))
    import app.utils.crypto_vault as cv
    monkeypatch.setattr(cv, "derive_key", lambda pw, salt, n=2 ** 10, _o=cv.derive_key: _o(pw, salt, n))
    # Diálogos modales: responder "Sí" y no bloquear
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    from app.controllers.main_controller import MainController
    c = MainController()
    c.vault.setup("contraseña-de-prueba")
    c.vault.set_setting("owner_name", "Ing. Prueba")
    c.vault.save_stamp(stamp_png, STAMP_W_MM, STAMP_H_MM, confirmed=True)
    c.show_main_window()
    c._load_stamp()
    qtbot.addWidget(c.view)
    yield c
    c.render.stop()


def load(qtbot, ctrl, paths):
    ctrl.load_files(paths)
    qtbot.waitUntil(lambda: not ctrl.loader.isRunning() and bool(ctrl.job.documents), timeout=10000)
    qtbot.wait(50)


def test_full_flow(qtbot, ctrl, tmp_path):
    plan = make_pdf(str(tmp_path / "plano.pdf"), [ANSI_D] * 3, rotations=[0, 90, 0])
    report = make_pdf(str(tmp_path / "reporte.pdf"), [LETTER] * 4)
    load(qtbot, ctrl, [plan, report])
    job = ctrl.job

    # Perfiles: plano en todas las hojas, reporte solo en la última
    assert sorted(job.placements_for(plan)) == [0, 1, 2]
    assert job.documents[report].profile == PROFILE_REPORT
    assert list(job.placements_for(report)) == [3]

    # Mover y rotar en la hoja 1 del plano no afecta a las demás
    ctrl.view.navigator.select_page(plan, 1)
    assert ctrl.current == (plan, 1)
    other = job.placement(plan, 0)
    ctrl.view.canvas.stamp_committed.emit(700.0, 500.0, 37.0)
    pl = job.placement(plan, 1)
    assert (round(pl.cx), round(pl.cy), pl.rotation) == (700, 500, 37.0)
    assert job.placement(plan, 0) == other
    assert ctrl.view.canvas.current_state() == pytest.approx((700, 500, 37))

    # Flechas: 1 mm por pulsación, y se fusionan en un solo paso de deshacer
    for _ in range(3):
        ctrl.view.canvas.nudge_requested.emit(geometry.mm_to_pt(1), 0)
    assert job.placement(plan, 1).cx == pytest.approx(700 + geometry.mm_to_pt(3))
    ctrl.undo.undo()
    assert job.placement(plan, 1).cx == pytest.approx(700)

    # "Colocar sello aquí" en una hoja con sello lo MUEVE: nunca dos sellos
    ctrl.view.canvas.place_requested.emit(400.0, 400.0)
    assert len([k for k in job.placements_for(plan) if k == 1]) == 1
    assert (job.placement(plan, 1).cx, job.placement(plan, 1).cy) == (400.0, 400.0)

    # Copiar a todas las hojas del archivo reemplaza, no añade; deshacer lo revierte
    ctrl.copy_current_to([(plan, i) for i in range(3)], "todas")
    assert all(job.placement(plan, i).cx == 400.0 for i in range(3))
    assert job.sealed_page_count() == 4
    ctrl.undo.undo()
    assert job.placement(plan, 0) == other

    # Quitar y volver a poner
    ctrl.remove_current()
    assert job.placement(plan, 1) is None
    assert ctrl.view.navigator._pages[(plan, 1)].data(1, nav.ROLE_KEY) == nav.STATUS_NONE
    ctrl.place_default()
    assert job.placement(plan, 1) is not None

    # Sellar (procesos en paralelo)
    assert ctrl.view.btn_seal.isEnabled()
    ctrl.start_sealing()
    qtbot.waitUntil(lambda: ctrl.signer is None, timeout=60000)
    assert all(r["ok"] for r in ctrl._results), ctrl._results
    assert set(ctrl._done_docs) == {plan, report}
    out_plan = ctrl._done_docs[plan]
    assert os.path.basename(out_plan) == "SELLADO_plano.pdf"
    with pymupdf.open(out_plan) as d:
        assert seal_id.parse_keywords(d.metadata["keywords"])[1] == [0, 1, 2]
        assert all(len(p.get_images()) == 1 for p in d)
    assert not ctrl.view.btn_seal.isEnabled()

    # Verificación: emitido por mí
    state, title, _ = ctrl.verify_document(out_plan)
    assert state == "ok"
    # Modificado después: misma marca, hash distinto
    with pymupdf.open(out_plan) as d:
        d.save(str(tmp_path / "alterado.pdf"))
    assert ctrl.verify_document(str(tmp_path / "alterado.pdf"))[0] == "modified"
    assert ctrl.verify_document(plan)[0] == "unknown"

    # Re-abrir el PDF sellado: sus hojas selladas están bloqueadas y no admiten otro sello
    load(qtbot, ctrl, [out_plan])
    assert all(p.locked for p in job.documents[out_plan].pages)
    assert job.placements_for(out_plan) == {}
    ctrl.view.navigator.select_page(out_plan, 0)
    ctrl.view.canvas.place_requested.emit(300.0, 300.0)
    assert job.placement(out_plan, 0) is None


def test_session_roundtrip(qtbot, ctrl, tmp_path):
    plan = make_pdf(str(tmp_path / "plano.pdf"), [ANSI_D] * 2)
    load(qtbot, ctrl, [plan])
    ctrl.view.navigator.select_page(plan, 1)
    ctrl.view.canvas.stamp_committed.emit(800.0, 600.0, 15.0)
    ctrl.save_session()

    ctrl.job.clear()
    ctrl.view.navigator.clear_all()
    ctrl._offer_session_restore()
    qtbot.waitUntil(lambda: not ctrl.loader.isRunning() and bool(ctrl.job.documents), timeout=10000)
    qtbot.wait(50)
    pl = ctrl.job.placement(plan, 1)
    assert (pl.cx, pl.cy, pl.rotation) == (800.0, 600.0, 15.0)


def test_theme_toggle_and_lock_state(qtbot, ctrl):
    ctrl.toggle_theme()
    assert ctrl.view.theme == "dark"
    ctrl.toggle_theme()
    assert ctrl.view.theme == "light"
