import pytest
from PIL import Image, ImageDraw

from app.utils import stamp_image


def scan_with_tilted_stamp(angle=3.0, dpi=200):
    """Hoja blanca con un 'sello' rectangular inclinado y una mota suelta."""
    page = Image.new("RGB", (1200, 1600), "white")
    stamp = Image.new("RGB", (440, 230), "white")
    d = ImageDraw.Draw(stamp)
    d.rectangle((0, 0, 439, 229), outline="black", width=5)
    d.text((60, 60), "JOSE PRUEBA", fill="black")
    d.line((60, 150, 300, 140), fill=(20, 40, 170), width=4)
    stamp = stamp.rotate(angle, expand=True, fillcolor="white")
    page.paste(stamp, (300, 900))
    ImageDraw.Draw(page).ellipse((1100, 1500, 1110, 1510), fill="black")  # mota
    page.info["dpi"] = (dpi, dpi)
    return page


def test_prepare_scan_straightens_crops_and_measures():
    out, dpi, info = stamp_image.prepare_scan(scan_with_tilted_stamp(), dpi=200)
    assert out.mode == "RGBA"
    assert abs(info["angle"]) == pytest.approx(3.0, abs=0.6)
    # 440 px + 2 mm de margen a 200 dpi ≈ 55.9 + 2 mm
    assert info["width_mm"] == pytest.approx(440 / 200 * 25.4 + 2, abs=1.5)
    assert info["height_mm"] == pytest.approx(230 / 200 * 25.4 + 2, abs=1.5)
    # Esquinas transparentes, tinta opaca
    assert out.getpixel((0, 0))[3] == 0
    assert out.getchannel("A").getextrema()[1] == 255


def test_background_removal_keeps_blue_ink():
    img = Image.new("RGB", (10, 1), "white")
    img.putpixel((5, 0), (20, 40, 170))
    out = stamp_image.remove_white_background(img)
    assert out.getpixel((0, 0))[3] == 0
    r, g, b, a = out.getpixel((5, 0))
    assert a == 255 and b > r and b > g
