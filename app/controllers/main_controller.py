import json
import os

import pymupdf
from PyQt6.QtCore import QEvent, QObject, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QPixmap, QUndoCommand, QUndoStack
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

from app.models.placement import PROFILE_PLAN, Placement, SealJob, SealRuleError
from app.models.vault_model import VaultModel
from app.utils import geometry, pdf_stamper, seal_id, stamp_image
from app.utils.crypto_vault import VaultError
from app.utils.paths import get_app_data_path
from app.views import page_navigator as nav
from app.views.login_view import SetupDialog, UnlockDialog
from app.views.main_view import MainView
from app.views.stamp_dialog import StampDialog
from app.views.verify_view import VerifyDialog
from app.workers.loader_worker import FileLoaderWorker
from app.workers.render_worker import RenderWorker
from app.workers.signing_worker import SigningWorker

IDLE_LOCK_MINUTES = 15
SESSION_FILE = "session.json"

# Ids para fusionar comandos consecutivos de deshacer (p. ej. varios toques de flecha)
MERGE_NUDGE, MERGE_SPIN, MERGE_WHEEL = 1, 2, 3


class SetPlacementCommand(QUndoCommand):
    """Cambia el sello de una o varias hojas. Base de todo deshacer/rehacer."""

    def __init__(self, ctrl, changes, text, merge_id=-1):
        super().__init__(text)
        self.ctrl = ctrl
        self.changes = changes          # [(key, before, after)]
        self.merge_id = merge_id

    def redo(self):
        self.changes = [(k, b, self.ctrl.apply_placement(k, a)) for k, b, a in self.changes]
        self.ctrl.after_command([k for k, _, _ in self.changes])

    def undo(self):
        for k, b, _a in reversed(self.changes):
            self.ctrl.apply_placement(k, b)
        self.ctrl.after_command([k for k, _, _ in self.changes])

    def id(self):
        return self.merge_id

    def mergeWith(self, other):
        if len(self.changes) != 1 or len(other.changes) != 1 or self.changes[0][0] != other.changes[0][0]:
            return False
        k, b, _ = self.changes[0]
        self.changes = [(k, b, other.changes[0][2])]
        return True


class MainController(QObject):
    def __init__(self):
        super().__init__()
        self.vault = VaultModel()
        self.theme = self.vault.get_setting("theme", "light")
        self.view = None
        self.job = None
        self.stamp = None               # (png, w_mm, h_mm)
        self.current = None             # (path, page_index)
        self.undo = QUndoStack(self)
        self.render = None
        self.loader = None
        self.signer = None
        self._render_token = 0
        self._done_docs = {}            # path -> ruta de salida (sellado en esta sesión)
        self._errors = {}               # (path, idx) -> mensaje
        self._pending_pw = {}           # path -> owner password del lote en curso
        self._restore_data = None
        self._locked_ui = False

        self._idle = QTimer(self)
        self._idle.setInterval(IDLE_LOCK_MINUTES * 60 * 1000)
        self._idle.setSingleShot(True)
        self._idle.timeout.connect(lambda: self.lock_now(idle=True))
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(1500)
        self._save_timer.timeout.connect(self.save_session)

    # ======================================================================
    # Arranque y bóveda
    # ======================================================================
    def start(self):
        """Devuelve False si el usuario cancela el acceso."""
        if not self.vault.is_initialized():
            dlg = SetupDialog(self.theme)
            if not dlg.exec():
                return False
            name, password = dlg.values()
            self.vault.setup(password)
            self.vault.set_setting("owner_name", name)
        elif not self._ask_unlock():
            return False

        self._migrate_legacy()
        self.show_main_window()
        self._load_stamp()
        if self.stamp is None:
            QMessageBox.information(self.view, "Configura tu sello",
                                    "Antes de sellar, importa el escaneo de tu sello con firma.")
            self.open_stamp_dialog()
        self._offer_session_restore()
        return True

    def _ask_unlock(self, reason=""):
        dlg = UnlockDialog(self.theme, reason, self.view if self.view and self.view.isVisible() else None)
        failures = {"n": 0}

        def attempt():
            if self.vault.unlock(dlg.password()):
                dlg.accept()
                return
            failures["n"] += 1
            delay = min(30, 2 ** (failures["n"] - 1))
            dlg.show_error(f"Contraseña incorrecta. Espera {delay} s para reintentar.")
            dlg.clear()
            dlg.btn_ok.setEnabled(False)
            QTimer.singleShot(delay * 1000, lambda: dlg.btn_ok.setEnabled(True))

        dlg.btn_ok.clicked.connect(attempt)
        return bool(dlg.exec())

    def _migrate_legacy(self):
        """Firmas de la versión multiusuario guardadas en claro → bóveda cifrada."""
        paths = self.vault.legacy_signature_paths()
        if not paths:
            if self.vault.db.has_legacy_users():
                self.vault.drop_legacy_users()
            return
        if self.vault.load_stamp() is None:
            answer = QMessageBox.question(
                None, "Firma de la versión anterior",
                "Se encontró una imagen de firma de la versión anterior guardada SIN cifrar:\n\n"
                f"{paths[0]}\n\n¿Importarla a la bóveda cifrada? (luego podrás ajustar su tamaño real)")
            if answer == QMessageBox.StandardButton.Yes:
                with open(paths[0], "rb") as f:
                    data = f.read()
                img = stamp_image.from_bytes(data)
                w_mm, h_mm = stamp_image.physical_size_mm(img.width, img.height, stamp_image.image_dpi(img))
                self.vault.save_stamp(stamp_image.to_png_bytes(img.convert("RGBA")), w_mm, h_mm, False)
        answer = QMessageBox.question(
            None, "Borrar copias sin cifrar",
            "¿Borrar las copias sin cifrar de firmas de la versión anterior?\n\n" + "\n".join(paths))
        if answer == QMessageBox.StandardButton.Yes:
            for p in paths:
                try:
                    os.remove(p)
                except OSError:
                    pass
        self.vault.drop_legacy_users()

    def _load_stamp(self):
        self.stamp = self.vault.load_stamp()
        confirmed = self.vault.get_setting("stamp_size_confirmed", False)
        if self.stamp is None:
            self.view.properties.set_stamp_info(None, 0, 0, False)
            self._update_seal_button()
            return
        png, w_mm, h_mm = self.stamp
        bw_mm, bh_mm = pdf_stamper.block_size_mm(w_mm, h_mm)
        if self.job is None:
            self.job = SealJob(geometry.mm_to_pt(bw_mm), geometry.mm_to_pt(bh_mm))
        else:
            self.job.set_stamp_size(geometry.mm_to_pt(bw_mm), geometry.mm_to_pt(bh_mm))
        pm = QPixmap()
        pm.loadFromData(png)
        self.view.canvas.set_stamp_spec(pm, geometry.mm_to_pt(w_mm), geometry.mm_to_pt(h_mm),
                                        geometry.mm_to_pt(pdf_stamper.ID_STRIP_MM))
        self.view.properties.set_stamp_info(png, w_mm, h_mm, confirmed)
        self.refresh_all()

    # ======================================================================
    # Ventana principal
    # ======================================================================
    def show_main_window(self):
        v = self.view = MainView(self.vault.get_setting("owner_name", ""), self.theme)
        if self.job is None:
            self.job = SealJob(1, 1)   # se redimensiona al cargar el sello

        self.render = RenderWorker()
        self.render.page_rendered.connect(self._on_page_rendered)
        self.render.thumb_rendered.connect(v.navigator.set_thumbnail)
        self.render.start()

        v.act_open.triggered.connect(self.select_files)
        v.act_clear.triggered.connect(self.clear_all)
        v.act_stamp.triggered.connect(self.open_stamp_dialog)
        v.act_verify.triggered.connect(self.open_verify)
        v.act_undo.triggered.connect(self.undo.undo)
        v.act_redo.triggered.connect(self.undo.redo)
        self.undo.canUndoChanged.connect(v.act_undo.setEnabled)
        self.undo.canRedoChanged.connect(v.act_redo.setEnabled)
        v.act_undo.setEnabled(False)
        v.act_redo.setEnabled(False)
        v.act_zoom_in.triggered.connect(lambda: v.canvas.zoom_by(1.25))
        v.act_zoom_out.triggered.connect(lambda: v.canvas.zoom_by(0.8))
        v.act_fit.triggered.connect(v.canvas.fit_page)
        v.act_prev.triggered.connect(lambda: self.go_relative(-1))
        v.act_next.triggered.connect(lambda: self.go_relative(1))
        v.act_theme.triggered.connect(self.toggle_theme)
        v.act_lock.triggered.connect(self.lock_now)
        v.btn_seal.clicked.connect(self.start_sealing)
        v.btn_cancel.clicked.connect(self.cancel_sealing)
        v.closing.connect(self.shutdown)

        n = v.navigator
        n.page_selected.connect(self.show_page)
        n.files_dropped.connect(self.load_files)
        n.profile_change_requested.connect(self.change_profile)
        n.seal_all_requested.connect(self.seal_all_pages)
        n.clear_all_requested.connect(self.clear_file_seals)
        n.remove_file_requested.connect(self.remove_file)

        c = v.canvas
        c.files_dropped.connect(self.load_files)
        c.stamp_live.connect(v.properties.show_live)
        c.stamp_committed.connect(lambda x, y, r: self.edit_current(
            lambda pl: Placement(x, y, r, True), "Mover/rotar sello"))
        c.place_requested.connect(self.place_at)
        c.remove_requested.connect(self.remove_current)
        c.nudge_requested.connect(lambda dx, dy: self.edit_current(
            lambda pl: Placement(pl.cx + dx, pl.cy + dy, pl.rotation, True), "Mover sello", MERGE_NUDGE))
        c.rotate_by_requested.connect(self.rotate_by)
        c.render_requested.connect(self._request_render)

        p = v.properties
        p.place_clicked.connect(self.place_default)
        p.remove_clicked.connect(self.remove_current)
        p.reset_clicked.connect(self.reset_current)
        p.rotate_by_clicked.connect(self.rotate_by)
        p.values_edited.connect(lambda x, y, r: self.edit_current(
            lambda pl: Placement(x, y, r, True), "Editar posición", MERGE_SPIN))
        p.copy_selected_clicked.connect(lambda: self.copy_current_to(v.navigator.selected_pages(),
                                                                     "las hojas seleccionadas"))
        p.copy_file_clicked.connect(lambda: self.copy_current_to(
            [(self.current[0], pg.index) for pg in self.job.documents[self.current[0]].pages],
            "todas las hojas del archivo"))
        p.copy_all_clicked.connect(lambda: self.copy_current_to(
            [(d.path, pg.index) for d in self.job.documents.values() for pg in d.pages],
            "todas las hojas de todos los archivos"))
        p.profile_changed.connect(lambda prof: self.current and self.change_profile(self.current[0], prof))
        p.project_changed.connect(self._save_project)
        p.output_dir_clicked.connect(self.select_output_folder)
        p.output_dir_reset_clicked.connect(lambda: self._set_output_dir(None))
        p.stamp_settings_clicked.connect(self.open_stamp_dialog)
        p.set_project(self.vault.get_setting("project", ""), self.vault.get_setting("expediente", ""))
        out = self.vault.get_setting("output_dir")
        p.set_output_dir(out if out and os.path.isdir(out) else None)

        QApplication.instance().installEventFilter(self)
        self._idle.start()
        self._update_seal_button()
        v.show()

    def shutdown(self):
        self.save_session()
        if self.signer and self.signer.isRunning():
            self.signer.cancel()
            self.signer.wait(5000)
        if self.render:
            self.render.stop()
        QApplication.instance().removeEventFilter(self)
        QApplication.instance().quit()

    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self.vault.set_setting("theme", self.theme)
        self.view.set_theme(self.theme)
        self.refresh_all()

    # ======================================================================
    # Bloqueo por inactividad
    # ======================================================================
    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress, QEvent.Type.Wheel,
                            QEvent.Type.MouseMove):
            if not self._locked_ui:
                self._idle.start()
        return False

    def lock_now(self, idle=False):
        if self._locked_ui or self.view is None:
            return
        if self.signer and self.signer.isRunning():
            self._idle.start()   # no bloquear a mitad de un sellado
            return
        self._locked_ui = True
        self.save_session()
        self.vault.lock()
        self.stamp = None
        self.view.hide()
        reason = (f"La aplicación se bloqueó tras {IDLE_LOCK_MINUTES} minutos sin actividad."
                  if idle else "Aplicación bloqueada.")
        if self._ask_unlock(reason):
            self._locked_ui = False
            self.view.show()
            self._load_stamp()
            self._idle.start()
        else:
            self.view.close()

    # ======================================================================
    # Carga de archivos
    # ======================================================================
    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(self.view, "Abrir planos o reportes", "", "PDF (*.pdf)")
        if files:
            self.load_files(files)

    def load_files(self, paths):
        if not paths or (self.loader and self.loader.isRunning()):
            return
        index = {}
        for sha in self.vault.known_output_hashes():
            index[sha] = self.vault.sealed_pages_by_hash(sha)
        self.view.set_busy(True)
        self.view.set_status("Leyendo archivos…")
        self.loader = FileLoaderWorker(paths, index)
        self.loader.progress_updated.connect(self.view.progress.setValue)
        self.loader.finished_signal.connect(self._on_files_loaded)
        self.loader.start()

    def _on_files_loaded(self, docs, errors):
        self.view.set_busy(False)
        added = []
        for doc in docs:
            if self.job.add_document(doc):
                added.append(doc)
                self.view.navigator.add_document(doc)
        if self._restore_data:
            self.job.restore_placements(self._restore_data)
            self._restore_data = None
        self.refresh_all()
        self.render.request_thumbs([(d.path, p.index) for d in added for p in d.pages])
        locked = sum(p.locked for d in added for p in d.pages)
        msg = f"{len(added)} archivo{'s' if len(added) != 1 else ''} cargado{'s' if len(added) != 1 else ''}"
        if locked:
            msg += f" · {locked} hoja{'s' if locked != 1 else ''} ya sellada{'s' if locked != 1 else ''} (bloqueadas)"
        self.view.set_status(msg)
        if added and self.current is None:
            first = added[0]
            target = next((p.index for p in first.pages if self.job.placement(first.path, p.index)), 0)
            self.view.navigator.select_page(first.path, target)
        if errors:
            QMessageBox.warning(self.view, "Algunos archivos no se cargaron",
                                "\n".join(f"• {os.path.basename(p)}: {e}" for p, e in errors))
        self._schedule_save()

    def remove_file(self, path):
        self.job.remove_document(path)
        self.view.navigator.remove_document(path)
        self.render.forget(path)
        self._done_docs.pop(path, None)
        self.undo.clear()   # los comandos guardados podrían referirse a ese archivo
        if self.current and self.current[0] == path:
            self.current = None
            self.view.canvas.show_page(None, None, False)
            self.view.properties.show_page(None, None, None, False)
            order = self.view.navigator.page_order()
            if order:
                self.view.navigator.select_page(*order[0])
        self._update_seal_button()
        self._schedule_save()

    def clear_all(self):
        if not self.job.documents:
            return
        if QMessageBox.question(self.view, "Limpiar", "¿Quitar todos los archivos de la lista?") \
                != QMessageBox.StandardButton.Yes:
            return
        for path in list(self.job.documents):
            self.render.forget(path)
        self.job.clear()
        self.view.navigator.clear_all()
        self.undo.clear()
        self._done_docs.clear()
        self._errors.clear()
        self.current = None
        self.view.canvas.show_page(None, None, False)
        self.view.properties.show_page(None, None, None, False)
        self._update_seal_button()
        self._schedule_save()

    # ======================================================================
    # Hoja actual
    # ======================================================================
    def _is_locked(self, key):
        path, idx = key
        return self.job.page(path, idx).locked or path in self._done_docs

    def _banner(self, key):
        path, idx = key
        if path in self._done_docs:
            return f"Sellado en esta sesión → {os.path.basename(self._done_docs[path])}"
        return None

    def show_page(self, path, index):
        if path not in self.job.documents:
            return
        self.current = (path, index)
        doc = self.job.documents[path]
        page = doc.pages[index]
        placement = self.job.placement(path, index)
        locked = self._is_locked(self.current)
        self.view.canvas.show_page(page, placement, locked, self._banner(self.current))
        self.view.properties.show_page(doc, page, placement, locked)
        self._request_render(self.view.canvas.zoom_factor() * self.view.canvas.devicePixelRatioF())

    def go_relative(self, step):
        order = self.view.navigator.page_order()
        if not order:
            return
        i = order.index(self.current) if self.current in order else -1
        self.view.navigator.select_page(*order[max(0, min(len(order) - 1, i + step))])

    def _request_render(self, scale):
        if self.current is None:
            return
        self._render_token += 1
        self.render.request_page(self._render_token, self.current[0], self.current[1], scale)

    def _on_page_rendered(self, token, path, index, scale, image):
        if token == self._render_token and self.current == (path, index):
            self.view.canvas.set_page_image(image, scale)

    # ======================================================================
    # Edición (todo pasa por comandos de deshacer)
    # ======================================================================
    def apply_placement(self, key, placement):
        """Aplica al modelo y refresca la vista. Devuelve la colocación real (ajustada a la hoja)."""
        path, idx = key
        if path not in self.job.documents:
            return placement
        actual = self.job.set_placement(path, idx, placement)
        self._refresh_page(key)
        return actual

    def after_command(self, keys):
        """Tras hacer/deshacer: refrescar; si el cambio fue en UNA hoja distinta de la actual, ir a ella
        (en cambios de varias hojas, como copiar, se queda en la hoja actual)."""
        if len(keys) == 1 and self.current not in keys and keys[0][0] in self.job.documents:
            self.view.navigator.select_page(*keys[0])
        elif self.current in keys:
            path, idx = self.current
            pl = self.job.placement(path, idx)
            self.view.canvas.update_placement(pl)
            doc = self.job.documents[path]
            self.view.properties.show_page(doc, doc.pages[idx], pl, self._is_locked(self.current))
        self._update_file_labels({k[0] for k in keys})
        self._update_seal_button()
        self._schedule_save()

    def _push(self, changes, text, merge_id=-1):
        changes = [(k, b, a) for k, b, a in changes if b != a]
        if not changes:
            return
        try:
            self.undo.push(SetPlacementCommand(self, changes, text, merge_id))
        except SealRuleError as e:
            self.view.set_status(str(e))

    def _editable_current(self):
        if self.current is None or self._is_locked(self.current):
            return None
        return self.current

    def edit_current(self, fn, text, merge_id=-1):
        key = self._editable_current()
        if key is None:
            return
        before = self.job.placement(*key)
        if before is None:
            return
        self._push([(key, before, fn(before))], text, merge_id)

    def place_at(self, x, y):
        """Colocar el sello en (x, y). Si la hoja ya tiene sello, se MUEVE (nunca dos)."""
        key = self._editable_current()
        if key is None:
            return
        before = self.job.placement(*key)
        rot = before.rotation if before else 0.0
        self._push([(key, before, Placement(x, y, rot, True))],
                   "Mover sello" if before else "Colocar sello")
        self.view.canvas.select_stamp()

    def place_default(self):
        key = self._editable_current()
        if key is None or self.job.placement(*key) is not None:
            return
        doc = self.job.documents[key[0]]
        try:
            pl = self.job.default_placement(doc.pages[key[1]], doc.profile)
        except SealRuleError as e:
            QMessageBox.warning(self.view, "No cabe", str(e))
            return
        self._push([(key, None, Placement(pl.cx, pl.cy, 0.0, True))], "Colocar sello")
        self.view.canvas.select_stamp()

    def remove_current(self):
        key = self._editable_current()
        if key and self.job.placement(*key) is not None:
            self._push([(key, self.job.placement(*key), None)], "Quitar sello")

    def reset_current(self):
        key = self._editable_current()
        if key is None:
            return
        doc = self.job.documents[key[0]]
        try:
            pl = self.job.default_placement(doc.pages[key[1]], doc.profile)
        except SealRuleError as e:
            QMessageBox.warning(self.view, "No cabe", str(e))
            return
        self._push([(key, self.job.placement(*key), pl)], "Restablecer sello")

    def rotate_by(self, deg):
        merge = MERGE_WHEEL if abs(deg) < 90 else -1
        self.edit_current(lambda pl: Placement(pl.cx, pl.cy, pl.rotation + deg, True), "Rotar sello", merge)

    def copy_current_to(self, targets, description):
        key = self._editable_current()
        if key is None or self.job.placement(*key) is None:
            return
        src = self.job.placement(*key)
        changes, skipped = [], 0
        for t in targets:
            if t == key:
                continue
            if self._is_locked(t):
                skipped += 1
                continue
            page = self.job.page(*t)
            if not geometry.fits_on_page(self.job.stamp_w, self.job.stamp_h, src.rotation, page.width, page.height):
                skipped += 1
                continue
            changes.append((t, self.job.placement(*t), Placement(src.cx, src.cy, src.rotation, True)))
        if not changes:
            self.view.set_status("No hay otras hojas a las que copiar.")
            return
        self._push(changes, f"Copiar sello a {description}")
        msg = f"Posición copiada a {len(changes)} hoja{'s' if len(changes) != 1 else ''}"
        if skipped:
            msg += f" · {skipped} omitida{'s' if skipped != 1 else ''} (bloqueadas o el sello no cabe)"
        self.view.set_status(msg)

    def seal_all_pages(self, path):
        doc = self.job.documents[path]
        changes = []
        for p in doc.pages:
            key = (path, p.index)
            if self._is_locked(key) or self.job.placement(*key) is not None:
                continue
            try:
                changes.append((key, None, self.job.default_placement(p, PROFILE_PLAN)))
            except SealRuleError:
                pass
        self._push(changes, "Poner sello en todas las hojas")

    def clear_file_seals(self, path):
        doc = self.job.documents[path]
        changes = [((path, p.index), self.job.placement(path, p.index), None)
                   for p in doc.pages if not self._is_locked((path, p.index))]
        self._push(changes, "Quitar sellos del archivo")

    def change_profile(self, path, profile):
        doc = self.job.documents.get(path)
        if doc is None or doc.profile == profile:
            return
        manual = any(pl.manual for pl in self.job.placements_for(path).values())
        if manual and QMessageBox.question(
                self.view, "Cambiar tipo de documento",
                "Cambiar el tipo restablece las posiciones del sello en todas las hojas de este archivo "
                "(podrás deshacerlo). ¿Continuar?") != QMessageBox.StandardButton.Yes:
            self.view.properties.show_page(doc, doc.pages[self.current[1]] if self.current else None,
                                           self.job.placement(*self.current) if self.current else None,
                                           self._is_locked(self.current) if self.current else False)
            return
        # Calcular las posiciones del nuevo perfil y registrarlas como un comando (deshacer):
        # se aplican, se anotan y se vuelve al estado previo para que el comando las re-aplique.
        before = {p.index: self.job.placement(path, p.index) for p in doc.pages}
        self.job.apply_profile(path, profile)
        after = {p.index: self.job.placement(path, p.index) for p in doc.pages}
        for idx, pl in before.items():
            if pl is None:
                self.job.remove(path, idx)
            else:
                self.job.set_placement(path, idx, pl)
        self._push([((path, i), before[i], after[i]) for i in before], "Cambiar tipo de documento")
        self._update_file_labels({path})

    # ======================================================================
    # Refresco de la vista
    # ======================================================================
    def _status_for(self, key):
        path, idx = key
        if key in self._errors:
            return nav.STATUS_ERROR
        if path in self._done_docs:
            return nav.STATUS_DONE if self.job.placement(*key) else (
                nav.STATUS_LOCKED if self.job.page(*key).locked else nav.STATUS_NONE)
        if self.job.page(*key).locked:
            return nav.STATUS_LOCKED
        pl = self.job.placement(*key)
        if pl is None:
            return nav.STATUS_NONE
        return nav.STATUS_MANUAL if pl.manual else nav.STATUS_PLACED

    def _refresh_page(self, key):
        self.view.navigator.set_page_status(*key, self._status_for(key), self._errors.get(key, ""))

    def _update_file_labels(self, paths):
        for path in paths:
            doc = self.job.documents.get(path)
            if doc:
                self.view.navigator.update_file_label(doc, len(self.job.placements_for(path)))

    def refresh_all(self):
        if self.view is None or self.job is None:
            return
        for doc in self.job.documents.values():
            for p in doc.pages:
                self._refresh_page((doc.path, p.index))
        self._update_file_labels(self.job.documents.keys())
        self._update_seal_button()
        if self.current and self.current[0] in self.job.documents:
            self.show_page(*self.current)

    def _pending_docs(self):
        return [d for d in self.job.documents.values()
                if d.path not in self._done_docs and self.job.placements_for(d.path)]

    def _update_seal_button(self):
        if self.view is None:
            return
        docs = self._pending_docs() if self.job else []
        pages = sum(len(self.job.placements_for(d.path)) for d in docs)
        self.view.set_seal_count(pages if self.stamp else 0, len(docs))

    # ======================================================================
    # Sello, proyecto y salida
    # ======================================================================
    def open_stamp_dialog(self):
        dlg = StampDialog(self.vault, self.theme, self.view)
        if dlg.exec():
            self._load_stamp()
            self.view.set_status("Sello actualizado.")

    def _save_project(self, project, expediente):
        self.vault.set_setting("project", project)
        self.vault.set_setting("expediente", expediente)

    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self.view, "Carpeta de salida")
        if folder:
            self._set_output_dir(folder)

    def _set_output_dir(self, folder):
        self.vault.set_setting("output_dir", folder)
        self.view.properties.set_output_dir(folder)

    # ======================================================================
    # Sellado
    # ======================================================================
    def start_sealing(self):
        if self.stamp is None:
            QMessageBox.warning(self.view, "Sin sello", "Configura tu sello antes de sellar.")
            return
        docs = self._pending_docs()
        if not docs:
            return
        if not self.vault.get_setting("stamp_size_confirmed", False):
            if QMessageBox.question(
                    self.view, "Tamaño no confirmado",
                    "Aún no confirmaste el tamaño real del sello midiéndolo con una regla.\n"
                    "¿Sellar de todas formas?") != QMessageBox.StandardButton.Yes:
                return

        png, w_mm, h_mm = self.stamp
        out_dir = self.vault.get_setting("output_dir")
        out_dir = out_dir if out_dir and os.path.isdir(out_dir) else None
        hmac_key = self.vault.hmac_key()
        owner = self.vault.get_setting("owner_name", "")
        project = self.vault.get_setting("project", "")
        expediente = self.vault.get_setting("expediente", "")
        jobs, taken = [], []
        self._pending_pw.clear()
        n_pages = 0
        for d in docs:
            placements = self.job.placements_for(d.path)
            out = pdf_stamper.output_path_for(d.path, out_dir, taken)
            taken.append(out)
            pw = pdf_stamper.generate_owner_password()
            self._pending_pw[d.path] = pw
            n_pages += len(placements)
            jobs.append({"key": d.path, "args": dict(
                src_path=d.path, out_path=out,
                placements=[(i, pl.cx, pl.cy, pl.rotation) for i, pl in sorted(placements.items())],
                stamp_png=png, stamp_w_mm=w_mm, stamp_h_mm=h_mm, hmac_key=hmac_key, owner_pw=pw,
                owner_name=owner, project=project, expediente=expediente)})

        dest = out_dir or "la misma carpeta de cada original"
        if QMessageBox.question(
                self.view, "Confirmar sellado",
                f"Se sellarán {n_pages} hoja{'s' if n_pages != 1 else ''} en {len(jobs)} "
                f"archivo{'s' if len(jobs) != 1 else ''}.\n\nDestino: {dest}\n"
                "Los originales no se modifican. ¿Continuar?") != QMessageBox.StandardButton.Yes:
            return

        for d in docs:
            for p in d.pages:
                self._errors.pop((d.path, p.index), None)
        self._results = []
        self.view.set_busy(True, cancellable=True)
        self.signer = SigningWorker(jobs)
        self.signer.progress_updated.connect(self.view.progress.setValue)
        self.signer.status_updated.connect(self.view.set_status)
        self.signer.job_finished.connect(self._on_job_finished)
        self.signer.finished_signal.connect(self._on_sealing_finished)
        self.signer.start()

    def cancel_sealing(self):
        if self.signer and self.signer.isRunning():
            self.signer.cancel()
            self.view.set_status("Cancelando… (los archivos en curso terminarán)")

    def _on_job_finished(self, result):
        self._results.append(result)
        path = result.get("key")
        if path not in self.job.documents:
            return
        if result["ok"]:
            self.vault.log_seal(result, self._pending_pw.pop(path, ""))
            self._done_docs[path] = result["out"]
        else:
            for idx in self.job.placements_for(path):
                self._errors[(path, idx)] = result.get("msg", "Error")
        for p in self.job.documents[path].pages:
            self._refresh_page((path, p.index))
        if self.current and self.current[0] == path:
            self.show_page(*self.current)

    def _on_sealing_finished(self, ok, failed, cancelled):
        self.view.set_busy(False)
        self._pending_pw.clear()
        self._update_seal_button()
        self.view.set_status(f"Sellado terminado: {ok} correcto{'s' if ok != 1 else ''}, "
                             f"{failed} con error" + (" (cancelado)" if cancelled else ""))
        lines = [f"Correctos: {ok}", f"Con error: {failed}"]
        if cancelled:
            lines.append("El proceso se canceló; algunos archivos no se sellaron.")
        errors = [r for r in self._results if not r["ok"]]
        if errors:
            lines.append("")
            lines += [f"• {os.path.basename(r.get('src') or '?')}: {r.get('msg')}" for r in errors[:10]]
        box = QMessageBox(self.view)
        box.setWindowTitle("Resultado del sellado")
        box.setIcon(QMessageBox.Icon.Warning if failed else QMessageBox.Icon.Information)
        box.setText("\n".join(lines))
        open_btn = None
        outs = [r["out"] for r in self._results if r["ok"]]
        if outs:
            open_btn = box.addButton("Abrir carpeta", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        if open_btn is not None and box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(outs[0])))
        self.signer = None

    # ======================================================================
    # Verificación
    # ======================================================================
    def verify_document(self, path):
        try:
            sha = seal_id.sha256_file(path)
        except OSError as e:
            return "error", "No se pudo leer el archivo", str(e)
        rows = self.vault.find_by_hash(sha)
        if rows:
            r = rows[0]
            pages = ", ".join(str(x["page_index"] + 1) for x in rows)
            ids = ", ".join(x["page_id"] for x in rows)
            return ("ok", "✔ Emitido por ti y sin modificar",
                    f"Sellado el {r['seal_date']} · documento {r['doc_id']}\n"
                    f"Hojas selladas: {pages}\nIDs: {ids}\nOriginal: {os.path.basename(r['src_path'])}")
        try:
            with pymupdf.open(path) as doc:
                marker = seal_id.parse_keywords((doc.metadata or {}).get("keywords", ""))
        except Exception as e:  # noqa: BLE001
            return "error", "No es un PDF válido", str(e)
        if marker:
            rows = self.vault.find_by_doc_id(marker[0])
            if rows:
                return ("modified", "⚠ Emitido por ti, pero MODIFICADO después",
                        f"El documento {marker[0]} se selló el {rows[0]['seal_date']}, pero su contenido "
                        "ya no coincide con el que emitiste (el hash es distinto).")
            return ("unknown", "✖ ID de sellado desconocido",
                    f"El PDF dice estar sellado con DigitalSealer (ID {marker[0]}), pero ese ID no está en "
                    "tu registro: no lo emitiste desde esta instalación.")
        return "unknown", "✖ No reconocido", "Este PDF no fue sellado por ti con esta aplicación."

    def open_verify(self):
        VerifyDialog(self.verify_document, self.theme, self.view).exec()

    # ======================================================================
    # Sesión
    # ======================================================================
    def _session_path(self):
        return os.path.join(get_app_data_path(), SESSION_FILE)

    def _schedule_save(self):
        self._save_timer.start()

    def save_session(self):
        if self.job is None:
            return
        data = self.job.to_dict()
        data["documents"] = [d for d in data["documents"] if d["path"] not in self._done_docs]
        try:
            with open(self._session_path(), "w", encoding="utf-8") as f:
                json.dump(data, f)
        except OSError:
            pass

    def _offer_session_restore(self):
        try:
            with open(self._session_path(), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        paths = [d["path"] for d in data.get("documents", []) if os.path.isfile(d.get("path", ""))]
        if not paths:
            return
        if QMessageBox.question(
                self.view, "Restaurar sesión",
                f"¿Reabrir los {len(paths)} archivo{'s' if len(paths) != 1 else ''} de la sesión anterior "
                "con las posiciones del sello?") == QMessageBox.StandardButton.Yes:
            self._restore_data = data
            self.load_files(paths)
