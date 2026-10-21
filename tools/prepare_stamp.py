"""
Prepara la imagen del sello+firma a partir de un escaneo.

Uso:
    python tools/prepare_stamp.py ENTRADA.png SALIDA.png [--y-min 900] [--dpi 200]

Pasos (ver app/utils/stamp_image.py):
  1. Recorta la región donde está el sello (y >= y_min) y aísla el mayor grupo de tinta.
  2. Endereza (deskew) usando el borde superior del marco.
  3. Recorta al marco + 1 mm de margen.
  4. Convierte el fondo blanco en transparencia conservando el color de la tinta.
  5. Guarda PNG RGBA con el DPI del escaneo e imprime el tamaño físico en mm.

Este script NO se empaqueta con la app; la salida no debe subirse al repositorio.
"""
import argparse
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.utils.stamp_image import prepare_scan  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--y-min", type=int, default=0, help="Fila (px) desde la que buscar el sello")
    ap.add_argument("--dpi", type=float, default=None, help="DPI del escaneo (por defecto, el del archivo)")
    args = ap.parse_args(argv)

    img = Image.open(args.src)
    region = (0, args.y_min, img.width, img.height) if args.y_min else None
    out, dpi, info = prepare_scan(img, dpi=args.dpi, region=region)
    out.save(args.dst, dpi=(dpi, dpi))

    print(f"Inclinación corregida: {info['angle']:.2f}°")
    print(f"Tamaño: {out.width}x{out.height} px @ {dpi:.0f} dpi = "
          f"{info['width_mm']:.1f} x {info['height_mm']:.1f} mm")


if __name__ == "__main__":
    sys.exit(main())
