import hashlib
import io

import pymupdf
import pytest
from PIL import Image

from app.models.placement import SealRuleError
from app.utils import geometry, pdf_stamper, seal_id
from tests.conftest import ANSI_D, LEGAL, LETTER, STAMP_H_MM, STAMP_W_MM

KEY = b"k" * 32
BLOCK_W_MM, BLOCK_H_MM = pdf_stamper.block_size_mm(STAMP_W_MM, STAMP_H_MM)


def stamp(src, placements, png, tmp_path, name="out.pdf"):
    out = str(tmp_path / name)
    result = pdf_stamper.stamp_document(src, out, placements, png, STAMP_W_MM, STAMP_H_MM,
                                        KEY, "owner-secret", "Ing. Prueba", "Proyecto X")
    return out, result


def image_boxes(page):
    """Cajas de imagen en coordenadas visuales."""
    return [pymupdf.Rect(i["bbox"]) * page.rotation_matrix for i in page.get_image_info()]


def test_real_scale_on_any_sheet(pdf_factory, stamp_png, tmp_path):
    src = pdf_factory([LETTER, LEGAL, ANSI_D])
    out, _ = stamp(src, [(0, 300, 400, 0), (1, 300, 500, 0), (2, 1200, 800, 0)], stamp_png, tmp_path)
    with pymupdf.open(out) as d:
        for page in d:
            (box,) = image_boxes(page)
            assert geometry.pt_to_mm(box.width) == pytest.approx(BLOCK_W_MM, abs=0.1)
            assert geometry.pt_to_mm(box.height) == pytest.approx(BLOCK_H_MM, abs=0.1)


@pytest.mark.parametrize("page_rot", [0, 90, 180, 270])
def test_position_and_rotation_per_page(pdf_factory, stamp_png, tmp_path, page_rot):
    src = pdf_factory([ANSI_D] * 3, rotations=[page_rot] * 3)
    with pymupdf.open(src) as d:
        pw, ph = d[0].rect.width, d[0].rect.height
    placements = [(0, 300, 300, 0.0), (1, pw / 2, ph / 2, 37.0), (2, pw - 200, ph - 200, 270.0)]
    out, result = stamp(src, placements, stamp_png, tmp_path)
    assert set(result["page_ids"]) == {0, 1, 2}
    bw, bh = geometry.mm_to_pt(BLOCK_W_MM), geometry.mm_to_pt(BLOCK_H_MM)
    with pymupdf.open(out) as d:
        for idx, cx, cy, rot in placements:
            (box,) = image_boxes(d[idx])
            ex0, ey0, ex1, ey1 = geometry.stamp_bbox(cx, cy, bw, bh, rot)
            assert (box.x0, box.y0, box.x1, box.y1) == pytest.approx((ex0, ey0, ex1, ey1), abs=0.6)


def test_rule_one_seal_per_page(pdf_factory, stamp_png, tmp_path):
    src = pdf_factory([ANSI_D])
    with pytest.raises(SealRuleError):
        stamp(src, [(0, 300, 300, 0), (0, 800, 600, 0)], stamp_png, tmp_path)


def test_already_sealed_pages_are_locked(pdf_factory, stamp_png, tmp_path):
    src = pdf_factory([LETTER] * 3)
    out, _ = stamp(src, [(2, 300, 600, 0)], stamp_png, tmp_path)
    with pymupdf.open(out) as d:
        assert seal_id.parse_keywords(d.metadata["keywords"])[1] == [2]
    with pytest.raises(SealRuleError):
        stamp(out, [(2, 300, 300, 0)], stamp_png, tmp_path, "twice.pdf")
    # Otra hoja del mismo documento sí se puede sellar, y la marca acumula ambas
    out2, _ = stamp(out, [(0, 300, 300, 0)], stamp_png, tmp_path, "other_page.pdf")
    with pymupdf.open(out2) as d:
        assert seal_id.parse_keywords(d.metadata["keywords"])[1] == [0, 2]


def test_stamp_does_not_fit_or_out_of_page(pdf_factory, stamp_png, tmp_path):
    src = pdf_factory([(100, 100)])
    with pytest.raises(SealRuleError):
        stamp(src, [(0, 50, 50, 0)], stamp_png, tmp_path)
    src = pdf_factory([LETTER])
    with pytest.raises(SealRuleError):
        stamp(src, [(0, 5, 5, 0)], stamp_png, tmp_path, "edge.pdf")


def test_security_properties(pdf_factory, stamp_png, tmp_path):
    src = pdf_factory([ANSI_D])
    out, result = stamp(src, [(0, 1000, 700, 15)], stamp_png, tmp_path)

    raw = open(out, "rb").read()
    assert b"/AESV3" in raw  # AES-256
    with pymupdf.open(out) as d:
        assert d.permissions & pymupdf.PDF_PERM_PRINT
        assert not d.permissions & pymupdf.PDF_PERM_MODIFY
        assert not d.permissions & pymupdf.PDF_PERM_COPY
        assert not d.permissions & pymupdf.PDF_PERM_ANNOTATE
        page = d[0]
        assert list(page.annots()) == []  # aplanado: nada editable
        assert not d.is_form_pdf

        images = page.get_images(full=True)
        assert len(images) == 1
        xref, smask = images[0][0], images[0][1]
        assert smask == 0  # sin canal alfa: no se puede separar del fondo
        extracted = d.extract_image(xref)["image"]
        # El sello original no está incrustado tal cual
        assert hashlib.sha256(extracted).digest() != hashlib.sha256(stamp_png).digest()
        assert Image.open(io.BytesIO(extracted)).mode == "RGB"

        assert result["doc_id"] in d.metadata["subject"]
        assert d.metadata["author"] == "Ing. Prueba"
    assert result["out_sha256"] == seal_id.sha256_file(out)


def test_output_path_never_overwrites(tmp_path):
    src = tmp_path / "plano.pdf"
    src.write_bytes(b"x")
    p1 = pdf_stamper.output_path_for(str(src))
    assert p1.endswith("SELLADO_plano.pdf")
    open(p1, "wb").close()
    p2 = pdf_stamper.output_path_for(str(src))
    assert p2 != p1 and p2.endswith("(2).pdf")


def test_run_job_reports_errors(pdf_factory, stamp_png, tmp_path):
    src = pdf_factory([ANSI_D])
    job = {"key": "x", "args": dict(src_path=src, out_path=str(tmp_path / "o.pdf"),
                                    placements=[(0, 1, 1, 0), (0, 2, 2, 0)], stamp_png=stamp_png,
                                    stamp_w_mm=STAMP_W_MM, stamp_h_mm=STAMP_H_MM, hmac_key=KEY,
                                    owner_pw="pw")}
    r = pdf_stamper.run_job(job)
    assert r["ok"] is False and "más de un sello" in r["msg"]


def test_seal_ids_are_keyed():
    a = seal_id.page_seal_id(b"a" * 32, "hash", 0, "2026-10-20")
    b = seal_id.page_seal_id(b"b" * 32, "hash", 0, "2026-10-20")
    c = seal_id.page_seal_id(b"a" * 32, "hash", 1, "2026-10-20")
    assert a != b and a != c and len(a) == 11


@pytest.mark.parametrize("page_rot", [0, 90, 270])
def test_cad_page_with_offset_boxes(tmp_path, stamp_png, page_rot):
    """Hoja tipo CAD (MediaBox/CropBox desplazados, rotada): el sello aparece donde
    se colocó en la vista. Se verifica por render (lo que realmente se imprime)."""
    import numpy as np

    src = str(tmp_path / "cad.pdf")
    doc = pymupdf.open()
    page = doc.new_page(width=ANSI_D[0] + 100, height=ANSI_D[1] + 80)
    page.set_mediabox(pymupdf.Rect(-30, 20, ANSI_D[0] + 70, ANSI_D[1] + 100))
    page.set_cropbox(pymupdf.Rect(40, 60, ANSI_D[0] + 10, ANSI_D[1] + 50))
    page.set_rotation(page_rot)
    doc.save(src)
    doc.close()

    with pymupdf.open(src) as d:
        pw, ph = d[0].rect.width, d[0].rect.height
    cx, cy, rot = pw * 0.7, ph * 0.6, 20.0
    out, _ = stamp(src, [(0, cx, cy, rot)], stamp_png, tmp_path)

    with pymupdf.open(out) as d:
        pix = d[0].get_pixmap(dpi=72)
    a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    ys, xs = np.where(a[:, :, :3].min(axis=2) < 128)  # tinta del sello / ID
    bw, bh = geometry.mm_to_pt(BLOCK_W_MM), geometry.mm_to_pt(BLOCK_H_MM)
    x0, y0, x1, y1 = geometry.stamp_bbox(cx, cy, bw, bh, rot)
    assert xs.min() >= x0 - 2 and xs.max() <= x1 + 2
    assert ys.min() >= y0 - 2 and ys.max() <= y1 + 2
    # y el centro de la tinta está cerca del centro colocado
    assert abs((xs.min() + xs.max()) / 2 - cx) < 8 and abs((ys.min() + ys.max()) / 2 - cy) < 8


def test_generated_owner_password_is_accepted(pdf_factory, stamp_png, tmp_path):
    pw = pdf_stamper.generate_owner_password()
    assert len(pw) <= 40
    src = pdf_factory([LETTER])
    out = str(tmp_path / "pw.pdf")
    pdf_stamper.stamp_document(src, out, [(0, 300, 400, 0)], stamp_png, STAMP_W_MM, STAMP_H_MM, KEY, pw)
    with pymupdf.open(out) as d:
        assert d.authenticate(pw) == 4  # 4 = autenticado como propietario


def test_assembled_document(pdf_factory, stamp_png, tmp_path):
    """Borrar e insertar hojas de otro PDF: la salida tiene exactamente las hojas elegidas,
    numeradas como documento final, y una hoja que venía sellada sigue bloqueada."""
    main = pdf_factory([ANSI_D] * 3, rotations=[0, 90, 0])
    other = pdf_factory([LETTER] * 2)
    sealed, _ = stamp(other, [(1, 300, 400, 0)], stamp_png, tmp_path, "otro_sellado.pdf")

    # Hoja 1 del principal, hoja 1 de otro, hoja 3 del principal, hoja 2 ya sellada de otro
    spec = [(main, 0), (other, 0), (main, 2), (sealed, 1)]
    out = str(tmp_path / "armado.pdf")
    result = pdf_stamper.stamp_document(
        main, out, [(0, 1200, 800, 0), (1, 300, 400, 15), (2, 1200, 800, 0)], stamp_png,
        STAMP_W_MM, STAMP_H_MM, KEY, "pw", project="X", pages_spec=spec)
    assert result["assembled"] and set(result["page_ids"]) == {0, 1, 2}
    with pymupdf.open(out) as d:
        assert d.page_count == 4
        assert [round(p.rect.width) for p in d] == [ANSI_D[0], LETTER[0], ANSI_D[0], LETTER[0]]
        assert seal_id.parse_keywords(d.metadata["keywords"])[1] == [0, 1, 2, 3]
        assert [len(p.get_images()) for p in d] == [1, 1, 1, 1]

    # La hoja que venía sellada no admite otro sello en el documento armado
    with pytest.raises(SealRuleError):
        pdf_stamper.stamp_document(main, str(tmp_path / "x.pdf"), [(3, 300, 400, 0)], stamp_png,
                                   STAMP_W_MM, STAMP_H_MM, KEY, "pw", pages_spec=spec)


def test_assembled_output_cannot_overwrite_a_source(pdf_factory, stamp_png, tmp_path):
    main = pdf_factory([LETTER])
    other = pdf_factory([LETTER])
    with pytest.raises(ValueError):
        pdf_stamper.stamp_document(main, other, [(0, 300, 400, 0)], stamp_png, STAMP_W_MM, STAMP_H_MM,
                                   KEY, "pw", pages_spec=[(main, 0), (other, 0)])
