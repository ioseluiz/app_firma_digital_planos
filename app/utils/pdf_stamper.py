"""
Estampado aplanado y seguro del sello+firma.

Para cada hoja con sello:
  1. Se compone el sello con una franja inferior con el ID único de la hoja y una
     micro-trama tenue con ese ID sobre el área del sello.
  2. Se renderiza a 300 dpi el fondo del plano bajo la caja del sello y se funde
     con el sello rotado → UNA imagen RGB opaca, sin canal alfa: el sello no se
     puede separar limpiamente del plano ni reutilizar sin arrastrar el fondo y el ID.
  3. La imagen se inserta en el contenido de la página (no como anotación) a
     tamaño físico real.
El documento se guarda con metadatos de sellado y cifrado AES-256 con permisos
restringidos (ver e imprimir; sin modificar, copiar ni anotar).

Sin dependencias de Qt: se ejecuta en procesos aparte (ProcessPoolExecutor).
"""
import datetime
import hashlib
import io
import os
import secrets
import tempfile

import pymupdf
from PIL import Image, ImageDraw, ImageFont
from pymupdf import mupdf

from app.models.placement import SealRuleError
from app.utils import geometry, seal_id

RENDER_DPI = 300
ID_STRIP_MM = 3.0           # franja con el ID bajo el sello (el sello conserva su tamaño real)
PATTERN_ALPHA = 22          # opacidad (0-255) de la micro-trama
OUTPUT_PREFIX = "SELLADO_"
PERMISSIONS = pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_PRINT_HQ


def block_size_mm(stamp_w_mm, stamp_h_mm):
    """Tamaño físico del bloque colocado en la hoja: sello + franja del ID."""
    return stamp_w_mm, stamp_h_mm + ID_STRIP_MM


def output_path_for(src_path, output_dir=None, taken=()):
    """Ruta de salida libre: no existe, no es el original ni está en `taken` (otras salidas del lote)."""
    folder = output_dir or os.path.dirname(src_path)
    base = OUTPUT_PREFIX + os.path.basename(src_path)
    candidate = os.path.join(folder, base)
    stem, ext = os.path.splitext(candidate)
    taken = {os.path.normcase(os.path.abspath(p)) for p in taken}
    n = 2
    while (os.path.exists(candidate) or os.path.abspath(candidate) == os.path.abspath(src_path)
           or os.path.normcase(os.path.abspath(candidate)) in taken):
        candidate = f"{stem} ({n}){ext}"
        n += 1
    return candidate


def visual_to_insert_rect(page, vis):
    """Rect visual (como se ve la hoja) → rect que esperan los métodos insert_* de PyMuPDF.

    Se usa la transformación autoritativa de MuPDF (pdf_page_transform: espacio PDF →
    visual) en lugar de `page.derotation_matrix`, porque PyMuPDF calcula mal el
    desplazamiento en hojas rotadas con CropBox/MediaBox desplazados (habitual en
    PDFs exportados desde CAD).
    """
    mediabox, ctm = mupdf.FzRect(), mupdf.FzMatrix()
    mupdf.pdf_page_transform(mupdf.pdf_page_from_fz_page(page.this), mediabox, ctm)
    pdf_to_visual = pymupdf.Matrix(ctm.a, ctm.b, ctm.c, ctm.d, ctm.e, ctm.f)
    return pymupdf.Rect(vis) * ~pdf_to_visual * page.transformation_matrix


def generate_owner_password():
    # 24 bytes → 32 caracteres (192 bits). MuPDF admite como máximo 40 caracteres.
    return secrets.token_urlsafe(24)


# ---------------------------------------------------------------------------
# Composición de la imagen del sello
# ---------------------------------------------------------------------------
def _font(px):
    for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return ImageFont.load_default(size=px)


def _fit_text(draw, text, max_w, start_px, min_px=8):
    px = start_px
    while px > min_px:
        font = _font(px)
        if draw.textlength(text, font=font) <= max_w:
            return font, text
        px -= 1
    font = _font(min_px)
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return font, text + "…"


def compose_block(stamp_rgba, w_px, h_px, strip_px, page_id, label):
    """Sello (w_px × h_px) + micro-trama + franja de `strip_px` con el ID. Devuelve RGBA."""
    block = Image.new("RGBA", (w_px, h_px + strip_px), (255, 255, 255, 0))

    # Micro-trama: el ID repetido, muy tenue, bajo la tinta del sello
    pattern = Image.new("RGBA", (w_px, h_px), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pattern)
    pfont = _font(max(6, h_px // 22))
    step_y = max(8, h_px // 12)
    tile = f"{page_id} "
    tile_w = max(1, int(pd.textlength(tile, font=pfont)))
    for row, y in enumerate(range(0, h_px, step_y)):
        offset = (row * tile_w // 3) % tile_w
        for x in range(-offset, w_px, tile_w):
            pd.text((x, y), tile, font=pfont, fill=(90, 90, 90, PATTERN_ALPHA))
    block.alpha_composite(pattern, (0, 0))

    stamp = stamp_rgba.resize((w_px, h_px), Image.LANCZOS)
    block.alpha_composite(stamp, (0, 0))

    # Franja del ID
    d = ImageDraw.Draw(block)
    font, text = _fit_text(d, label, w_px - 4, int(strip_px * 0.72))
    tw = d.textlength(text, font=font)
    d.text(((w_px - tw) / 2, h_px + strip_px * 0.08), text, font=font, fill=(20, 20, 20, 255))
    return block


def id_label(page_id, page_index, total_pages, date_iso, project=""):
    parts = []
    if project:
        parts.append(project)
    parts += [f"Hoja {page_index + 1}/{total_pages}", date_iso, f"ID {page_id}"]
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# Estampado
# ---------------------------------------------------------------------------
def _validate_placements(placements, page_count, locked_pages):
    seen = set()
    for item in placements:
        idx = item[0]
        if idx in seen:
            raise SealRuleError(f"Regla violada: más de un sello en la hoja {idx + 1}.")
        seen.add(idx)
        if not 0 <= idx < page_count:
            raise SealRuleError(f"La hoja {idx + 1} no existe.")
        if idx in locked_pages:
            raise SealRuleError(f"La hoja {idx + 1} ya fue sellada; no admite otro sello.")


def assemble_document(pages_spec, base_metadata_from=None):
    """Arma un PDF nuevo con las hojas indicadas [(pdf_origen, página), ...] en ese orden.

    Devuelve (documento, posiciones ya selladas): una hoja que venía sellada por
    DigitalSealer en su PDF de origen sigue bloqueada en el documento armado.
    """
    if not pages_spec:
        raise ValueError("El documento debe tener al menos una hoja.")
    out = pymupdf.open()
    sources, locked = {}, set()
    try:
        for pos, (path, index) in enumerate(pages_spec):
            src = sources.get(path)
            if src is None:
                if not os.path.isfile(path):
                    raise ValueError(f"No se encuentra el PDF de origen: {path}")
                src = sources[path] = pymupdf.open(path)
            if not 0 <= index < src.page_count:
                raise ValueError(f"{os.path.basename(path)} no tiene la hoja {index + 1}.")
            marker = seal_id.parse_keywords((src.metadata or {}).get("keywords", ""))
            if marker and index in marker[1]:
                locked.add(pos)
            out.insert_pdf(src, from_page=index, to_page=index)
        base = sources.get(base_metadata_from)
        if base is not None:
            md = {k: v for k, v in (base.metadata or {}).items()
                  if k in ("title", "author", "subject", "creator", "producer", "creationDate")}
            out.set_metadata(md)
    except Exception:
        out.close()
        raise
    finally:
        for src in sources.values():
            src.close()
    return out, locked


def stamp_document(src_path, out_path, placements, stamp_png, stamp_w_mm, stamp_h_mm,
                   hmac_key, owner_pw, owner_name="", project="", expediente="", date_iso=None,
                   pages_spec=None):
    """Sella `src_path` y guarda en `out_path`.

    placements: lista de (page_index, cx_pt, cy_pt, rotation_deg) en coordenadas
    visuales; como máximo uno por hoja (se valida).
    pages_spec: si se indica [(pdf_origen, página), ...], primero se arma el documento
    final con esas hojas (borradas, reordenadas o insertadas de otros PDFs) y los
    índices de `placements` se refieren a ese documento armado.
    Devuelve dict con hashes, IDs y páginas selladas.
    """
    if os.path.abspath(src_path) == os.path.abspath(out_path):
        raise ValueError("El archivo de salida no puede ser el original.")
    if pages_spec and any(os.path.abspath(p) == os.path.abspath(out_path) for p, _ in pages_spec):
        raise ValueError("El archivo de salida no puede ser uno de los PDFs de origen.")
    date_iso = date_iso or datetime.date.today().isoformat()

    stamp = Image.open(io.BytesIO(stamp_png)).convert("RGBA")
    w_pt, h_pt = geometry.mm_to_pt(stamp_w_mm), geometry.mm_to_pt(stamp_h_mm)
    strip_pt = geometry.mm_to_pt(ID_STRIP_MM)
    block_w_pt, block_h_pt = w_pt, h_pt + strip_pt

    if pages_spec:
        doc, locked = assemble_document(pages_spec, base_metadata_from=src_path)
        # El ID se liga al contenido del documento armado
        src_sha = hashlib.sha256(doc.tobytes()).hexdigest()
    else:
        src_sha = seal_id.sha256_file(src_path)
        doc = pymupdf.open(src_path)
        previous = seal_id.parse_keywords((doc.metadata or {}).get("keywords", ""))
        locked = set(previous[1]) if previous else set()
    try:
        _validate_placements(placements, doc.page_count, locked)

        doc_id = seal_id.document_seal_id(hmac_key, src_sha, date_iso)
        page_ids = {}
        scale = RENDER_DPI / 72.0

        for page_index, cx, cy, rotation in placements:
            page = doc[page_index]
            pr = page.rect
            if not geometry.fits_on_page(block_w_pt, block_h_pt, rotation, pr.width, pr.height):
                raise SealRuleError(f"El sello no cabe en la hoja {page_index + 1}.")
            x0, y0, x1, y1 = geometry.stamp_bbox(cx, cy, block_w_pt, block_h_pt, rotation)
            tol = 0.5
            if x0 < -tol or y0 < -tol or x1 > pr.width + tol or y1 > pr.height + tol:
                raise SealRuleError(f"El sello se sale de la hoja {page_index + 1}.")
            vis = pymupdf.Rect(max(0, x0), max(0, y0), min(pr.width, x1), min(pr.height, y1))

            pid = seal_id.page_seal_id(hmac_key, src_sha, page_index, date_iso)
            page_ids[page_index] = pid
            label = id_label(pid, page_index, doc.page_count, date_iso, project)

            # Fondo del plano bajo el sello (coordenadas visuales)
            pix = page.get_pixmap(clip=vis, dpi=RENDER_DPI, alpha=False)
            bg = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

            # Sello+ID a la misma escala que el fondo, rotado y centrado
            block = compose_block(stamp, max(1, round(w_pt * scale)), max(1, round(h_pt * scale)),
                                  max(1, round(strip_pt * scale)), pid, label)
            if rotation:
                block = block.rotate(-rotation, resample=Image.BICUBIC, expand=True)
            ox = round((cx - vis.x0) * scale - block.width / 2)
            oy = round((cy - vis.y0) * scale - block.height / 2)
            bg.paste(block, (ox, oy), block)

            fused = io.BytesIO()
            bg.save(fused, "PNG", compress_level=6)

            # Insertar en el contenido de la página
            page.insert_image(visual_to_insert_rect(page, vis), stream=fused.getvalue(), rotate=page.rotation,
                              keep_proportion=False, overlay=True)

        sealed_pages = sorted(locked | set(page_ids))
        md = dict(doc.metadata or {})
        md.update({
            "author": owner_name or md.get("author", ""),
            "subject": f"Sellado por {owner_name} · ID {doc_id}" + (f" · Exp. {expediente}" if expediente else ""),
            "keywords": seal_id.build_keywords(doc_id, sealed_pages),
            "creator": "DigitalSealer",
            "modDate": pymupdf.get_pdf_now(),
        })
        md.pop("format", None)
        md.pop("encryption", None)
        doc.set_metadata(md)

        # Guardado atómico: temporal en la misma carpeta y luego renombrar
        out_dir = os.path.dirname(os.path.abspath(out_path))
        fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=out_dir)
        os.close(fd)
        enc = dict(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw=owner_pw, user_pw="",
                   permissions=PERMISSIONS)
        try:
            try:
                doc.save(tmp, garbage=3, deflate=True, **enc)
            except Exception:
                # Plan B (planos CAD pesados): guardado sin optimizar los streams
                doc.save(tmp, **enc)
            os.replace(tmp, out_path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    finally:
        doc.close()

    return {
        "ok": True,
        "src": src_path,
        "out": out_path,
        "src_sha256": src_sha,
        "out_sha256": seal_id.sha256_file(out_path),
        "doc_id": doc_id,
        "page_ids": page_ids,
        "date": date_iso,
        "assembled": bool(pages_spec),
    }


def run_job(job):
    """Punto de entrada para el pool de procesos. Nunca lanza: devuelve dict con ok/msg."""
    try:
        result = stamp_document(**job["args"])
        result["key"] = job.get("key")
        return result
    except Exception as e:  # noqa: BLE001 - el error se muestra en la UI
        return {"ok": False, "key": job.get("key"), "src": job["args"].get("src_path"), "msg": str(e)}
