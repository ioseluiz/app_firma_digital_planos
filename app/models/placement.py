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

    @property
    def name(self):
        return os.path.basename(self.path)

    def suggested_profile(self):
        return PROFILE_REPORT if self.pages and all(p.is_report for p in self.pages) else PROFILE_PLAN


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

    # ---------------------------------------------------------------- serial
    def to_dict(self):
        return {
            "documents": [
                {
                    "path": d.path,
                    "profile": d.profile,
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
