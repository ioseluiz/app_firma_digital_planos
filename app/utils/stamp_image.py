"""
Procesado de la imagen escaneada del sello+firma.

- Aísla el sello (mayor grupo de tinta), lo endereza y recorta.
- Convierte el fondo blanco en transparencia conservando el color de la tinta.
- Calcula el tamaño físico (mm) a partir del DPI del escaneo.

Sin dependencias de Qt: se usa también desde `tools/prepare_stamp.py`.
"""
import io

import numpy as np
from PIL import Image

INK_THRESHOLD = 110      # min(R,G,B) por debajo de esto se considera tinta (detección del marco)
ALPHA_LOW = 45           # oscuridad por debajo de la cual el píxel es totalmente transparente
ALPHA_HIGH = 150         # oscuridad a partir de la cual el píxel es totalmente opaco
DEFAULT_DPI = 200.0


def image_dpi(img):
    dpi = img.info.get("dpi")
    if dpi and dpi[0] and float(dpi[0]) > 1:
        return float(dpi[0])
    return DEFAULT_DPI


def physical_size_mm(width_px, height_px, dpi):
    return width_px / dpi * 25.4, height_px / dpi * 25.4


def ink_mask(rgb):
    return np.asarray(rgb).min(axis=2) < INK_THRESHOLD


def largest_ink_bbox(mask, block=8):
    """Caja (x0, y0, x1, y1) del mayor grupo de tinta, ignorando motas y marcas sueltas.

    Se reduce la máscara a bloques de `block` px (dilatación gruesa) y se busca la
    componente conexa más grande en esa rejilla.
    """
    if not mask.any():
        raise ValueError("No se encontró tinta en la imagen.")
    h, w = mask.shape
    gh, gw = -(-h // block), -(-w // block)
    padded = np.zeros((gh * block, gw * block), bool)
    padded[:h, :w] = mask
    grid = padded.reshape(gh, block, gw, block).any(axis=(1, 3))

    seen = np.zeros_like(grid)
    best, best_size = None, 0
    for sy, sx in zip(*np.where(grid)):
        if seen[sy, sx]:
            continue
        stack, cells = [(sy, sx)], []
        seen[sy, sx] = True
        while stack:
            y, x = stack.pop()
            cells.append((y, x))
            for ny in (y - 1, y, y + 1):
                for nx in (x - 1, x, x + 1):
                    if 0 <= ny < gh and 0 <= nx < gw and grid[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
        if len(cells) > best_size:
            best, best_size = cells, len(cells)

    cy = [c[0] for c in best]
    cx = [c[1] for c in best]
    gy0, gy1, gx0, gx1 = min(cy) * block, (max(cy) + 1) * block, min(cx) * block, (max(cx) + 1) * block
    ys, xs = np.where(mask[gy0:gy1, gx0:gx1])
    return gx0 + xs.min(), gy0 + ys.min(), gx0 + xs.max(), gy0 + ys.max()


def skew_angle(mask):
    """Ángulo (grados) del borde superior del marco, por regresión robusta."""
    x0, y0, x1, y1 = largest_ink_bbox(mask)
    xs, tops = [], []
    # Ignoramos los extremos (esquinas) y tomamos el primer píxel de tinta por columna
    for x in range(x0 + (x1 - x0) // 10, x1 - (x1 - x0) // 10):
        col = np.where(mask[y0:y1 + 1, x])[0]
        if len(col):
            xs.append(x)
            tops.append(y0 + col[0])
    if len(xs) < 10:
        return 0.0
    xs, tops = np.array(xs, float), np.array(tops, float)
    keep = np.ones_like(xs, bool)
    a = 0.0
    for _ in range(3):  # descartar atípicos (letras que asoman, manchas)
        a, b = np.polyfit(xs[keep], tops[keep], 1)
        resid = np.abs(tops - (a * xs + b))
        keep = resid < max(2.0, np.median(resid[keep]) * 3)
    return float(np.degrees(np.arctan(a)))


def isolate_and_straighten(img, dpi, region=None, margin_mm=1.0):
    """Recorta el sello, lo endereza y deja `margin_mm` de margen. Devuelve (imagen RGB, ángulo)."""
    img = img.convert("RGB")
    if region:
        img = img.crop(region)

    # Aislar el sello con holgura antes de medir la inclinación
    bx0, by0, bx1, by1 = largest_ink_bbox(ink_mask(img))
    pad = int(dpi / 4)
    img = img.crop((max(0, bx0 - pad), max(0, by0 - pad),
                    min(img.width, bx1 + pad), min(img.height, by1 + pad)))
    angle = skew_angle(ink_mask(img))

    # Pillow rota en sentido antihorario con ángulo positivo
    straight = img.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255))
    x0, y0, x1, y1 = largest_ink_bbox(ink_mask(straight), block=3)
    margin = int(round(dpi * margin_mm / 25.4))
    box = (max(0, x0 - margin), max(0, y0 - margin),
           min(straight.width, x1 + margin + 1), min(straight.height, y1 + margin + 1))
    return straight.crop(box), angle


def remove_white_background(img):
    """Fondo blanco → transparente, conservando el color de la tinta (azul de la firma, negro del sello)."""
    rgb = np.asarray(img.convert("RGB")).astype(np.float32)
    darkness = 255.0 - rgb.min(axis=2)
    alpha = np.clip((darkness - ALPHA_LOW) / (ALPHA_HIGH - ALPHA_LOW), 0.0, 1.0)
    # "Des-mezclar" del blanco para que la tinta no quede lavada
    safe = np.maximum(alpha, 1e-3)[..., None]
    out = np.clip(255.0 - (255.0 - rgb) / safe, 0, 255)
    return Image.fromarray(np.dstack([out, alpha * 255.0]).astype(np.uint8), "RGBA")


def prepare_scan(img, dpi=None, region=None, straighten=True, remove_background=True):
    """Pipeline completo. Devuelve (imagen RGBA, dpi, info dict)."""
    dpi = dpi or image_dpi(img)
    angle = 0.0
    if straighten:
        img, angle = isolate_and_straighten(img, dpi, region)
    elif region:
        img = img.crop(region)
    img = remove_white_background(img) if remove_background else img.convert("RGBA")
    w_mm, h_mm = physical_size_mm(img.width, img.height, dpi)
    return img, dpi, {"angle": angle, "width_mm": w_mm, "height_mm": h_mm}


def to_png_bytes(img, dpi=None):
    buf = io.BytesIO()
    kwargs = {"dpi": (dpi, dpi)} if dpi else {}
    img.save(buf, "PNG", **kwargs)
    return buf.getvalue()


def from_bytes(data):
    img = Image.open(io.BytesIO(data))
    img.load()
    return img
