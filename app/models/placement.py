"""
Modelo del trabajo de sellado (sin dependencias de Qt).

REGLA DE NEGOCIO: como máximo UN sello por hoja.
Se garantiza por estructura: las colocaciones se guardan en un diccionario
(archivo, hoja) → Placement, por lo que es imposible tener dos en la misma hoja.
`place()` sobre una hoja que ya tiene sello solo lo mueve.
"""
import os
from dataclasses import dataclass, field, replace

from app.utils import geometry

PROFILE_PLAN = "plano"
PROFILE_REPORT = "reporte"

# Posición inicial: distancia del borde del sello a los bordes de la hoja
_PLAN_MARGIN_MM = 20.0          # esquina inferior derecha, junto al cuadro de rótulo
_REPORT_BOTTOM_MM = 30.0        # zona de firma de un reporte
_REPORT_RIGHT_MM = 25.0


class SealRuleError(Exception):
    """Operación que violaría una regla de sellado."""


def parse_page_ranges(text, total):
    """'1-3, 5' → [0, 1, 2, 4] (índices base 0, en el orden escrito). Vacío o 'todas' = todas."""
    text = (text or "").strip().lower()
    if text in ("", "todas", "todo", "*"):
        return list(range(total))
    result = []
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                a, b = (int(x) for x in part.split("-", 1))
                step = 1 if b >= a else -1
                nums = range(a, b + step, step)
            else:
                nums = [int(part)]
        except ValueError:
            raise ValueError(f"No entiendo «{part}». Usa números y rangos, p. ej.: 1-3, 5") from None
        for n in nums:
            if not 1 <= n <= total:
                raise ValueError(f"La hoja {n} no existe (el PDF tiene {total}).")
            result.append(n - 1)
    if not result:
        raise ValueError("No se indicó ninguna hoja.")
    return result


@dataclass(frozen=True)
class Placement:
    """Sello en una hoja. Centro en coordenadas visuales (pt) y ángulo horario (°)."""
    cx: float
    cy: float
    rotation: float = 0.0
    manual: bool = False   # True si el usuario lo ajustó a mano


@dataclass
class PageInfo:
    index: int
    width: float           # visual, pt
    height: float          # visual, pt
    rotation: int = 0      # page.rotation del PDF
    locked: bool = False   # ya sellada por DigitalSealer: no admite otro sello
    src_path: str = None   # PDF de origen de la hoja (None = el propio documento)
    src_index: int = None  # página en el PDF de origen (None = `index` original)

    @property
    def format_name(self):
        return geometry.format_label(self.width, self.height)

    @property
    def is_report(self):
        return geometry.is_report_size(self.width, self.height)


@dataclass
class DocumentEntry:
    path: str
    pages: list = field(default_factory=list)
    profile: str = PROFILE_PLAN
    sha256: str = ""
    original_count: int = None   # hojas del PDF original (para detectar cambios)

    def __post_init__(self):
        if self.original_count is None:
            self.original_count = len(self.pages)

    @property
    def name(self):
        return os.path.basename(self.path)

    def suggested_profile(self):
        return PROFILE_REPORT if self.pages and all(p.is_report for p in self.pages) else PROFILE_PLAN

    def source(self, page):
        """(PDF de origen, página de origen) de una hoja."""
        return (page.src_path or self.path,
                page.src_index if page.src_index is not None else page.index)

    def page_sources(self):
        return [self.source(p) for p in self.pages]

    def is_modified(self):
        """True si se borraron, reordenaron o insertaron hojas respecto al PDF original."""
        return (self.original_count != len(self.pages)
                or self.page_sources() != [(self.path, i) for i in range(len(self.pages))])


class SealJob:
    def __init__(self, stamp_w_pt, stamp_h_pt):
        self.stamp_w = stamp_w_pt
        self.stamp_h = stamp_h_pt
        self.documents = {}      # path -> DocumentEntry (orden de inserción)
        self._placements = {}    # (path, page_index) -> Placement

    # ------------------------------------------------------------------ docs
    def add_document(self, doc, apply_profile=True):
        if doc.path in self.documents:
            return False
        if apply_profile:
            doc.profile = doc.suggested_profile()
        self.documents[doc.path] = doc
        if apply_profile:
            self.apply_profile(doc.path, doc.profile)
        return True

    def remove_document(self, path):
        self.documents.pop(path, None)
        for key in [k for k in self._placements if k[0] == path]:
            del self._placements[key]

    def clear(self):
        self.documents.clear()
        self._placements.clear()

    def page(self, path, index):
        return self.documents[path].pages[index]

    def set_stamp_size(self, w_pt, h_pt):
        """Cambia el tamaño del sello y re-ajusta las colocaciones a los límites."""
        self.stamp_w, self.stamp_h = w_pt, h_pt
        for key, pl in list(self._placements.items()):
            page = self.page(*key)
            try:
                cx, cy = self._clamp(page, pl.cx, pl.cy, pl.rotation)
                self._placements[key] = replace(pl, cx=cx, cy=cy)
            except SealRuleError:
                del self._placements[key]

    # -------------------------------------------------------------- defaults
    def default_placement(self, page, profile):
        w, h = self.stamp_w, self.stamp_h
        if profile == PROFILE_REPORT:
            cx = page.width - geometry.mm_to_pt(_REPORT_RIGHT_MM) - w / 2
            cy = page.height - geometry.mm_to_pt(_REPORT_BOTTOM_MM) - h / 2
        else:
            m = geometry.mm_to_pt(_PLAN_MARGIN_MM)
            cx = page.width - m - w / 2
            cy = page.height - m - h / 2
        cx, cy = self._clamp(page, cx, cy, 0.0)
        return Placement(cx, cy, 0.0)

    def apply_profile(self, path, profile):
        """Recrea las colocaciones iniciales del archivo según el perfil.

        Plano: un sello en todas las hojas. Reporte: solo en la última hoja.
        Las hojas bloqueadas (ya selladas) se omiten.
        """
        doc = self.documents[path]
        doc.profile = profile
        for p in doc.pages:
            self._placements.pop((path, p.index), None)
        targets = doc.pages if profile == PROFILE_PLAN else doc.pages[-1:]
        for p in targets:
            if not p.locked:
                try:
                    self._placements[(path, p.index)] = self.default_placement(p, profile)
                except SealRuleError:
                    pass  # hoja demasiado pequeña para el sello

    # ------------------------------------------------------------ placements
    def placement(self, path, index):
        return self._placements.get((path, index))

    def set_placement(self, path, index, placement):
        """Fija (o quita con None) el sello de una hoja. Base de deshacer/rehacer."""
        page = self.page(path, index)
        if placement is None:
            self._placements.pop((path, index), None)
            return None
        if page.locked:
            raise SealRuleError("Esta hoja ya fue sellada; no admite otro sello.")
        cx, cy = self._clamp(page, placement.cx, placement.cy, placement.rotation)
        placement = replace(placement, cx=cx, cy=cy,
                            rotation=geometry.normalize_angle(placement.rotation))
        self._placements[(path, index)] = placement
        return placement

    def place(self, path, index, cx, cy, rotation=None):
        """Coloca el sello de la hoja en (cx, cy). Si ya hay uno, lo MUEVE (nunca crea otro)."""
        current = self.placement(path, index)
        rot = rotation if rotation is not None else (current.rotation if current else 0.0)
        return self.set_placement(path, index, Placement(cx, cy, rot, manual=True))

    def move(self, path, index, cx, cy):
        current = self._require(path, index)
        return self.set_placement(path, index, replace(current, cx=cx, cy=cy, manual=True))

    def rotate_to(self, path, index, deg):
        current = self._require(path, index)
        return self.set_placement(path, index, replace(current, rotation=deg, manual=True))

    def remove(self, path, index):
        self._placements.pop((path, index), None)

    def copy_to(self, src_path, src_index, targets):
        """Copia posición+rotación a otras hojas, REEMPLAZANDO su sello (nunca añade uno extra).

        Devuelve (copiadas, omitidas). Se omiten hojas bloqueadas o donde el sello no cabe.
        """
        src = self._require(src_path, src_index)
        done, skipped = [], []
        for path, index in targets:
            if (path, index) == (src_path, src_index):
                continue
            try:
                self.set_placement(path, index, replace(src, manual=True))
                done.append((path, index))
            except SealRuleError:
                skipped.append((path, index))
        return done, skipped

    def placements_for(self, path):
        """{page_index: Placement} del archivo (un único sello por hoja)."""
        return {i: pl for (p, i), pl in self._placements.items() if p == path}

    def sealed_page_count(self):
        return len(self._placements)

    # ------------------------------------------------------- armar documento
    def _materialize_sources(self, doc):
        """Fija el origen de cada hoja antes de cambiar el orden (los índices cambiarán)."""
        for p in doc.pages:
            src_path, src_index = doc.source(p)
            p.src_path, p.src_index = src_path, src_index

    def _rebuild(self, path, new_pages):
        """Aplica un nuevo orden de hojas. `new_pages` son PageInfo (existentes o nuevos);
        las colocaciones viajan con su hoja."""
        doc = self.documents[path]
        old_placements = {id(p): self._placements.pop((path, p.index), None) for p in doc.pages}
        for i, p in enumerate(new_pages):
            p.index = i
        doc.pages = list(new_pages)
        for p in doc.pages:
            pl = old_placements.get(id(p))
            if pl is not None:
                self._placements[(path, p.index)] = pl

    def delete_pages(self, path, indices):
        doc = self.documents[path]
        indices = set(indices)
        if len(indices) >= len(doc.pages):
            raise SealRuleError("El documento debe conservar al menos una hoja.")
        self._materialize_sources(doc)
        self._rebuild(path, [p for p in doc.pages if p.index not in indices])

    def insert_pages(self, path, at, new_pages):
        """Inserta hojas (PageInfo con src_path/src_index) en la posición `at`.
        En un plano reciben un sello en la posición inicial; las bloqueadas no."""
        doc = self.documents[path]
        self._materialize_sources(doc)
        at = max(0, min(at, len(doc.pages)))
        self._rebuild(path, doc.pages[:at] + list(new_pages) + doc.pages[at:])
        if doc.profile == PROFILE_PLAN:
            for p in new_pages:
                if not p.locked:
                    try:
                        self._placements[(path, p.index)] = self.default_placement(p, doc.profile)
                    except SealRuleError:
                        pass

    def move_page(self, path, index, delta):
        doc = self.documents[path]
        target = index + delta
        if not 0 <= target < len(doc.pages):
            return index
        self._materialize_sources(doc)
        pages = list(doc.pages)
        pages.insert(target, pages.pop(index))
        self._rebuild(path, pages)
        return target

    def snapshot(self, path):
        """Estado completo de un documento (hojas + sellos), para deshacer/rehacer."""
        doc = self.documents[path]
        return {
            "pages": [replace(p) for p in doc.pages],
            "placements": dict(self.placements_for(path)),
            "profile": doc.profile,
        }

    def restore(self, path, snap):
        doc = self.documents[path]
        for p in doc.pages:
            self._placements.pop((path, p.index), None)
        doc.pages = [replace(p) for p in snap["pages"]]
        doc.profile = snap["profile"]
        for idx, pl in snap["placements"].items():
            self._placements[(path, idx)] = pl

    # ---------------------------------------------------------------- serial
    def to_dict(self):
        return {
            "documents": [
                {
                    "path": d.path,
                    "profile": d.profile,
                    "pages": d.page_sources() if d.is_modified() else None,
                    "placements": {
                        str(i): [pl.cx, pl.cy, pl.rotation, pl.manual]
                        for i, pl in sorted(self.placements_for(d.path).items())
                    },
                }
                for d in self.documents.values()
            ]
        }

    def restore_placements(self, data):
        """Aplica posiciones guardadas a documentos ya cargados (los que coincidan)."""
        for d in data.get("documents", []):
            path = d.get("path")
            if path not in self.documents:
                continue
            doc = self.documents[path]
            doc.profile = d.get("profile", doc.profile)
            for p in doc.pages:
                self._placements.pop((path, p.index), None)
            for idx, (cx, cy, rot, manual) in d.get("placements", {}).items():
                idx = int(idx)
                if idx < len(doc.pages):
                    try:
                        self.set_placement(path, idx, Placement(cx, cy, rot, manual))
                    except SealRuleError:
                        pass

    # --------------------------------------------------------------- helpers
    def _require(self, path, index):
        current = self.placement(path, index)
        if current is None:
            raise SealRuleError("La hoja no tiene sello.")
        return current

    def _clamp(self, page, cx, cy, rotation):
        try:
            return geometry.clamp_center(cx, cy, self.stamp_w, self.stamp_h, rotation,
                                         page.width, page.height)
        except ValueError as e:
            raise SealRuleError(str(e)) from e
