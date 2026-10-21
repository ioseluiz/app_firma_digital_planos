import pytest

from app.models.placement import (
    PROFILE_PLAN, PROFILE_REPORT, DocumentEntry, PageInfo, Placement, SealJob, SealRuleError,
)
from app.utils import geometry
from tests.conftest import ANSI_D, LETTER, STAMP_H_MM, STAMP_W_MM


def make_job():
    return SealJob(geometry.mm_to_pt(STAMP_W_MM), geometry.mm_to_pt(STAMP_H_MM))


def doc(path, sizes, locked=()):
    return DocumentEntry(path, [PageInfo(i, w, h, locked=i in locked) for i, (w, h) in enumerate(sizes)])


def test_plan_profile_seals_every_page():
    job = make_job()
    job.add_document(doc("plano.pdf", [ANSI_D] * 3))
    assert job.documents["plano.pdf"].profile == PROFILE_PLAN
    assert sorted(job.placements_for("plano.pdf")) == [0, 1, 2]


def test_report_profile_seals_only_last_page():
    job = make_job()
    job.add_document(doc("reporte.pdf", [LETTER] * 5))
    assert job.documents["reporte.pdf"].profile == PROFILE_REPORT
    assert list(job.placements_for("reporte.pdf")) == [4]


def test_mixed_document_is_plan():
    job = make_job()
    job.add_document(doc("mixto.pdf", [LETTER, ANSI_D]))
    assert job.documents["mixto.pdf"].profile == PROFILE_PLAN


def test_place_on_page_with_seal_moves_instead_of_adding():
    """REGLA: nunca dos sellos en la misma hoja."""
    job = make_job()
    job.add_document(doc("a.pdf", [ANSI_D]))
    job.place("a.pdf", 0, 500, 400)
    job.place("a.pdf", 0, 900, 700)
    placements = job.placements_for("a.pdf")
    assert len(placements) == 1
    assert (placements[0].cx, placements[0].cy) == (900, 700)


def test_copy_to_replaces_never_adds():
    job = make_job()
    job.add_document(doc("a.pdf", [ANSI_D] * 3))
    job.set_placement("a.pdf", 0, Placement(600, 500, 37))
    done, skipped = job.copy_to("a.pdf", 0, [("a.pdf", 1), ("a.pdf", 2)])
    assert len(done) == 2 and not skipped
    assert job.sealed_page_count() == 3
    for i in (1, 2):
        pl = job.placement("a.pdf", i)
        assert (pl.cx, pl.cy, pl.rotation) == (600, 500, 37)


def test_pages_are_independent():
    job = make_job()
    job.add_document(doc("a.pdf", [ANSI_D] * 2))
    before = job.placement("a.pdf", 1)
    job.move("a.pdf", 0, 300, 300)
    job.rotate_to("a.pdf", 0, 45)
    assert job.placement("a.pdf", 1) == before


def test_locked_page_rejects_seal():
    job = make_job()
    job.add_document(doc("a.pdf", [ANSI_D] * 2, locked={0}))
    assert job.placement("a.pdf", 0) is None
    assert job.placement("a.pdf", 1) is not None
    with pytest.raises(SealRuleError):
        job.place("a.pdf", 0, 500, 500)
    done, skipped = job.copy_to("a.pdf", 1, [("a.pdf", 0)])
    assert skipped == [("a.pdf", 0)] and not done


def test_placement_is_clamped_inside_page():
    job = make_job()
    job.add_document(doc("a.pdf", [LETTER]))
    pl = job.place("a.pdf", 0, -1000, 99999, rotation=30)
    x0, y0, x1, y1 = geometry.stamp_bbox(pl.cx, pl.cy, job.stamp_w, job.stamp_h, pl.rotation)
    assert x0 >= -1e-6 and y0 >= -1e-6 and x1 <= LETTER[0] + 1e-6 and y1 <= LETTER[1] + 1e-6


def test_rotation_free_angle_normalized():
    job = make_job()
    job.add_document(doc("a.pdf", [ANSI_D]))
    assert job.rotate_to("a.pdf", 0, -23.5).rotation == pytest.approx(336.5)


def test_serialization_roundtrip():
    job = make_job()
    job.add_document(doc("a.pdf", [ANSI_D] * 2))
    job.set_placement("a.pdf", 1, Placement(700, 600, 12, True))
    data = job.to_dict()

    job2 = make_job()
    job2.add_document(doc("a.pdf", [ANSI_D] * 2))
    job2.remove("a.pdf", 0)
    job2.restore_placements(data)
    assert job2.placement("a.pdf", 1) == Placement(700, 600, 12, True)
    assert job2.placement("a.pdf", 0) == job.placement("a.pdf", 0)
