import io
import os
import sys

import pymupdf
import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STAMP_W_MM = 55.0
STAMP_H_MM = 27.0
LETTER = (612, 792)
LEGAL = (612, 1008)
ANSI_D = (34 * 72, 22 * 72)


@pytest.fixture
def stamp_png():
    """Sello sintético (no el real): marco negro + 'firma' azul, fondo transparente, 200 dpi."""
    w, h = round(STAMP_W_MM / 25.4 * 200), round(STAMP_H_MM / 25.4 * 200)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((2, 2, w - 3, h - 3), outline=(0, 0, 0, 255), width=4)
    d.text((20, 20), "SELLO DE PRUEBA", fill=(0, 0, 0, 255))
    d.line((30, h - 60, w - 40, h - 70), fill=(20, 40, 160, 255), width=3)
    buf = io.BytesIO()
    img.save(buf, "PNG", dpi=(200, 200))
    return buf.getvalue()


def make_pdf(path, sizes, rotations=None, text=True):
    """PDF con una hoja por tamaño (w, h) en pt, con líneas y texto de fondo."""
    doc = pymupdf.open()
    rotations = rotations or [0] * len(sizes)
    for (w, h), rot in zip(sizes, rotations):
        page = doc.new_page(width=w, height=h)
        for x in range(0, int(w), 36):
            page.draw_line((x, 0), (x, h), color=(0.5, 0.5, 0.8), width=0.5)
        if text:
            page.insert_text((40, h - 60), "Texto de fondo del documento " * 4, fontsize=9)
        if rot:
            page.set_rotation(rot)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def pdf_factory(tmp_path):
    counter = {"n": 0}

    def factory(sizes, rotations=None):
        counter["n"] += 1
        return make_pdf(str(tmp_path / f"doc{counter['n']}.pdf"), sizes, rotations)

    return factory
