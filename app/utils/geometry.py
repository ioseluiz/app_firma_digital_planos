"""
Geometría de hoja y sello.

Convenciones:
- Unidades internas: puntos PDF (1 pt = 1/72 in).
- Coordenadas "visuales": la hoja tal como se ve en pantalla (ya aplicada
  `page.rotation`), origen arriba-izquierda, Y hacia abajo. Todo el editor y el
  modelo trabajan en este sistema.
- El ángulo del sello es en grados, sentido horario en pantalla (igual que Qt).
- La conversión a coordenadas internas del PDF (sin rotar) se hace con
  `page.derotation_matrix` de PyMuPDF en `pdf_stamper`.
"""
import math

MM_TO_PT = 72.0 / 25.4
PT_TO_MM = 25.4 / 72.0
IN_TO_PT = 72.0


def mm_to_pt(mm):
    return mm * MM_TO_PT


def pt_to_mm(pt):
    return pt * PT_TO_MM


def normalize_angle(deg):
    """Ángulo en [0, 360)."""
    a = math.fmod(deg, 360.0)
    if a < 0:
        a += 360.0
    # Evitar 359.9999999 por errores de redondeo
    return 0.0 if abs(a - 360.0) < 1e-9 else a


def rotated_size(w, h, deg):
    """Ancho y alto de la caja envolvente de un rectángulo w×h rotado `deg` grados."""
    r = math.radians(deg)
    c, s = abs(math.cos(r)), abs(math.sin(r))
    return w * c + h * s, w * s + h * c


def stamp_bbox(cx, cy, w, h, deg):
    """Caja envolvente (x0, y0, x1, y1) del sello centrado en (cx, cy)."""
    bw, bh = rotated_size(w, h, deg)
    return cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2


def fits_on_page(w, h, deg, page_w, page_h):
    bw, bh = rotated_size(w, h, deg)
    return bw <= page_w + 1e-6 and bh <= page_h + 1e-6


def clamp_center(cx, cy, w, h, deg, page_w, page_h):
    """Ajusta el centro para que el sello rotado quede dentro de la hoja."""
    bw, bh = rotated_size(w, h, deg)
    if bw > page_w or bh > page_h:
        raise ValueError("El sello no cabe en esta hoja con esa rotación.")
    cx = min(max(cx, bw / 2), page_w - bw / 2)
    cy = min(max(cy, bh / 2), page_h - bh / 2)
    return cx, cy


# ---------------------------------------------------------------------------
# Formatos de hoja
# ---------------------------------------------------------------------------
# (nombre, lado corto, lado largo) en pulgadas
_FORMATS_IN = [
    ("Carta", 8.5, 11),
    ("Oficio", 8.5, 13),
    ("Legal", 8.5, 14),
    ("Tabloide", 11, 17),
    ("ANSI C", 17, 22),
    ("ANSI D", 22, 34),
    ("ANSI E", 34, 44),
    ("ARCH A", 9, 12),
    ("ARCH B", 12, 18),
    ("ARCH C", 18, 24),
    ("ARCH D", 24, 36),
    ("ARCH E1", 30, 42),
    ("ARCH E", 36, 48),
]
# (nombre, lado corto, lado largo) en mm
_FORMATS_MM = [
    ("A4", 210, 297),
    ("A3", 297, 420),
    ("A2", 420, 594),
    ("A1", 594, 841),
    ("A0", 841, 1189),
]

_FORMATS_PT = [(n, a * IN_TO_PT, b * IN_TO_PT) for n, a, b in _FORMATS_IN] + [
    (n, a * MM_TO_PT, b * MM_TO_PT) for n, a, b in _FORMATS_MM
]

# Hojas hasta tamaño Legal (8.5×14 in) se consideran "reporte"
_REPORT_MAX_LONG_PT = 14.2 * IN_TO_PT
_REPORT_MAX_SHORT_PT = 8.8 * IN_TO_PT


def detect_format(w_pt, h_pt, tolerance=0.02):
    """Nombre del formato estándar de la hoja, o None si no coincide con ninguno."""
    short, long_ = sorted((w_pt, h_pt))
    for name, fs, fl in _FORMATS_PT:
        if abs(short - fs) <= fs * tolerance and abs(long_ - fl) <= fl * tolerance:
            return name
    return None


def is_report_size(w_pt, h_pt):
    """True si la hoja es de tamaño reporte (Carta, Oficio, Legal, A4 o menor)."""
    short, long_ = sorted((w_pt, h_pt))
    return long_ <= _REPORT_MAX_LONG_PT and short <= _REPORT_MAX_SHORT_PT


def format_label(w_pt, h_pt):
    name = detect_format(w_pt, h_pt)
    if name:
        return name
    return f"{pt_to_mm(w_pt):.0f}×{pt_to_mm(h_pt):.0f} mm"
