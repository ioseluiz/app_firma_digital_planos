import math

import pymupdf
import pytest

from app.utils import geometry
from tests.conftest import ANSI_D, LEGAL, LETTER


def test_mm_pt_roundtrip():
    assert geometry.mm_to_pt(25.4) == pytest.approx(72.0)
    assert geometry.pt_to_mm(geometry.mm_to_pt(57.0)) == pytest.approx(57.0)


@pytest.mark.parametrize("deg", [0, 37, 90, 135, 180, 270, 359])
def test_rotated_size_matches_corners(deg):
    w, h = 160.0, 90.0
    bw, bh = geometry.rotated_size(w, h, deg)
    r = math.radians(deg)
    xs, ys = [], []
    for x, y in [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]:
        xs.append(x * math.cos(r) - y * math.sin(r))
        ys.append(x * math.sin(r) + y * math.cos(r))
    assert bw == pytest.approx(max(xs) - min(xs))
    assert bh == pytest.approx(max(ys) - min(ys))


def test_normalize_angle():
    assert geometry.normalize_angle(-90) == 270
    assert geometry.normalize_angle(450) == 90
    assert geometry.normalize_angle(360) == 0


def test_clamp_center_keeps_rotated_stamp_on_page():
    cx, cy = geometry.clamp_center(-50, 5000, 160, 90, 37, 612, 792)
    x0, y0, x1, y1 = geometry.stamp_bbox(cx, cy, 160, 90, 37)
    assert x0 >= -1e-6 and y0 >= -1e-6 and x1 <= 612 + 1e-6 and y1 <= 792 + 1e-6


def test_clamp_center_too_big():
    with pytest.raises(ValueError):
        geometry.clamp_center(10, 10, 700, 90, 0, 612, 792)


@pytest.mark.parametrize("size,name,report", [
    (LETTER, "Carta", True),
    ((792, 612), "Carta", True),
    (LEGAL, "Legal", True),
    ((595.3, 841.9), "A4", True),
    (ANSI_D, "ANSI D", False),
    ((36 * 72, 24 * 72), "ARCH D", False),
    ((1191, 842), "A3", False),
])
def test_detect_format(size, name, report):
    assert geometry.detect_format(*size) == name
    assert geometry.is_report_size(*size) is report


def test_unknown_format_label():
    assert geometry.detect_format(500, 500) is None
    assert "mm" in geometry.format_label(500, 500)


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_pymupdf_visual_to_pdf_roundtrip(rot):
    """La conversión visual → PDF (derotation_matrix) es la inversa de rotation_matrix."""
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=400)
    page.set_rotation(rot)
    vis = pymupdf.Rect(100, 50, 200, 80)
    unrot = vis * page.derotation_matrix
    back = unrot * page.rotation_matrix
    assert (back.x0, back.y0, back.x1, back.y1) == pytest.approx((vis.x0, vis.y0, vis.x1, vis.y1))


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
@pytest.mark.parametrize("mediabox,cropbox", [
    (None, None),
    (None, (50, 30, 650, 430)),
    ((-20, 10, 680, 520), (13, 77, 600, 460)),
])
def test_insert_rect_with_offset_boxes(rot, mediabox, cropbox):
    """Hojas con MediaBox/CropBox desplazados (PDFs de CAD) y rotadas: la imagen
    insertada aparece exactamente en la caja visual y derecha."""
    import io

    from PIL import Image

    from app.utils.pdf_stamper import visual_to_insert_rect

    img = Image.new("RGB", (100, 50), (0, 0, 255))
    img.paste((255, 0, 0), (0, 0, 100, 25))  # mitad superior roja
    buf = io.BytesIO()
    img.save(buf, "PNG")

    doc = pymupdf.open()
    page = doc.new_page(width=700, height=500)
    if mediabox:
        page.set_mediabox(pymupdf.Rect(*mediabox))
    if cropbox:
        page.set_cropbox(pymupdf.Rect(*cropbox))
    page.set_rotation(rot)
    vis = pymupdf.Rect(100, 60, 200, 110)
    page.insert_image(visual_to_insert_rect(page, vis), stream=buf.getvalue(),
                      rotate=page.rotation, keep_proportion=False)

    pix = page.get_pixmap(clip=pymupdf.Rect(90, 50, 210, 120))
    # 10 px de margen blanco alrededor, rojo arriba y azul abajo dentro de la caja
    assert pix.pixel(5, 5) == (255, 255, 255)
    top, bottom = pix.pixel(60, 22), pix.pixel(60, 48)
    assert top[0] > 200 and top[2] < 60
    assert bottom[2] > 200 and bottom[0] < 60
