"""
Benchmark de sellado: secuencial vs. paralelo, y desglose de tiempo por etapa.

Uso:
    python tools/benchmark.py [--docs 12] [--pages 3] [--stamp RUTA.png]

Genera planos ANSI D sintéticos con mucho contenido vectorial (similar a un
plano CAD), los sella y reporta tiempos. Sirve para decidir dónde optimizar.
"""
import argparse
import cProfile
import io
import os
import pstats
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymupdf  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from app.utils import pdf_stamper  # noqa: E402

ANSI_D = (34 * 72, 22 * 72)


def make_plan(path, pages, heavy=False):
    doc = pymupdf.open()
    raster = None
    if heavy:
        # Imagen de fondo tipo ortofoto/escaneo (~ruido) para simular PDFs de CAD pesados
        import numpy as np
        rng = np.random.default_rng(0)
        arr = (rng.random((2200, 3400, 3)) * 255).astype("uint8")
        buf = io.BytesIO()
        Image.fromarray(arr).save(buf, "JPEG", quality=85)
        raster = buf.getvalue()
    w, h = ANSI_D
    for n in range(pages):
        page = doc.new_page(width=w, height=h)
        shape = page.new_shape()
        # ~6.000 segmentos por hoja: rejilla densa + "muros"
        for x in range(60, int(w) - 60, 12):
            shape.draw_line((x, 60), (x, h - 60))
        for y in range(60, int(h) - 60, 12):
            shape.draw_line((60, y), (w - 60, y))
        shape.finish(color=(0.4, 0.4, 0.4), width=0.3)
        for i in range(400):
            x, y = 100 + (i * 37) % int(w - 300), 100 + (i * 53) % int(h - 300)
            shape.draw_rect(pymupdf.Rect(x, y, x + 120, y + 8))
        shape.finish(color=(0, 0, 0), fill=(0.8, 0.8, 0.8), width=0.8)
        shape.commit()
        if raster:
            page.insert_image(pymupdf.Rect(60, 60, w - 600, h - 60), stream=raster, overlay=False)
        for i in range(60):
            page.insert_text((80 + (i % 6) * 380, 90 + (i // 6) * 140), f"COTA {n}-{i} 3.25 m", fontsize=7)
    doc.save(path, deflate=True)
    doc.close()


def synthetic_stamp():
    img = Image.new("RGBA", (440, 230), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((2, 2, 437, 227), outline=(0, 0, 0, 255), width=4)
    d.text((30, 30), "SELLO DE PRUEBA", fill=(0, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG", dpi=(200, 200))
    return buf.getvalue()


def make_job(src, out_dir, stamp_png, pages):
    w, h = ANSI_D
    return {"key": src, "args": dict(
        src_path=src, out_path=os.path.join(out_dir, "SELLADO_" + os.path.basename(src)),
        placements=[(i, w - 250, h - 200, 0.0) for i in range(pages)], stamp_png=stamp_png,
        stamp_w_mm=57.0, stamp_h_mm=29.2, hmac_key=b"k" * 32, owner_pw="benchmark-owner-pw",
        owner_name="Benchmark", project="Bench")}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", type=int, default=12)
    ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--stamp", default=None)
    ap.add_argument("--heavy", action="store_true", help="planos con raster embebido (PDF pesado)")
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args(argv)

    stamp_png = open(args.stamp, "rb").read() if args.stamp else synthetic_stamp()
    with tempfile.TemporaryDirectory() as tmp:
        srcs = []
        for i in range(args.docs):
            p = os.path.join(tmp, f"plano_{i:02d}.pdf")
            make_plan(p, args.pages, args.heavy)
            srcs.append(p)
        size_mb = sum(os.path.getsize(p) for p in srcs) / 1e6
        print(f"{args.docs} planos ANSI D × {args.pages} hojas ({size_mb:.1f} MB en total)")

        out1 = os.path.join(tmp, "seq")
        os.makedirs(out1)
        jobs = [make_job(s, out1, stamp_png, args.pages) for s in srcs]
        t = time.perf_counter()
        for j in jobs:
            assert pdf_stamper.run_job(j)["ok"]
        seq = time.perf_counter() - t
        print(f"Secuencial: {seq:6.2f} s  ({seq / (args.docs * args.pages) * 1000:.0f} ms/hoja)")

        out2 = os.path.join(tmp, "par")
        os.makedirs(out2)
        jobs = [make_job(s, out2, stamp_png, args.pages) for s in srcs]
        workers = args.workers or max(1, (os.cpu_count() or 2) - 1)
        t = time.perf_counter()
        with ProcessPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(pdf_stamper.run_job, jobs))
        par = time.perf_counter() - t
        assert all(r["ok"] for r in results)
        print(f"Paralelo ({workers} procesos): {par:6.2f} s  → {seq / par:.1f}× más rápido")

        # Desglose: ¿dónde se va el tiempo? (un documento, perfilado)
        out3 = os.path.join(tmp, "prof")
        os.makedirs(out3)
        prof = cProfile.Profile()
        prof.enable()
        pdf_stamper.run_job(make_job(srcs[0], out3, stamp_png, args.pages))
        prof.disable()
        stats = pstats.Stats(prof)
        total = sum(v[3] for v in stats.stats.values() if v[3] > 0) or 1
        buckets = {"render fondo 300 dpi (MuPDF, C)": ("get_pixmap",),
                   "guardar + comprimir + AES (MuPDF, C)": ("save",),
                   "composición imagen (Pillow, C)": ("compose_block", "rotate", "paste"),
                   "PNG del sello fundido (Pillow/zlib, C)": ("_save", "PngImagePlugin"),
                   "hash SHA-256 (hashlib, C)": ("sha256_file",)}
        print("\nDesglose de un documento:")
        stamp_total = next(v[3] for k, v in stats.stats.items() if k[2] == "stamp_document")
        for label, names in buckets.items():
            secs = max((v[3] for k, v in stats.stats.items() if any(n == k[2] or n in k[0] for n in names)),
                       default=0.0)
            print(f"  {label:42s} {secs:6.3f} s  ({secs / stamp_total * 100:4.0f} %)")
        print(f"  {'total stamp_document':42s} {stamp_total:6.3f} s")


if __name__ == "__main__":
    main()
