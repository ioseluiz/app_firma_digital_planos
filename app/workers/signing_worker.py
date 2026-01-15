from PyQt6.QtCore import QThread, pyqtSignal
from app.utils.pdf_stamper import PDFStamper
import os

class SigningWorker(QThread):
    # Señales para comunicar progreso
    progress_updated = pyqtSignal(int)       # % total
    status_updated = pyqtSignal(str)         # Mensaje de estado inferior
    finished_signal = pyqtSignal(str)        # Reporte final
    
    # NUEVA SEÑAL: (Índice en lista, Éxito?, Mensaje Error/Exito)
    file_processed = pyqtSignal(int, bool, str)

    def __init__(self, files, sig_path, output_dir, coords):
        super().__init__()
        self.files = files
        self.sig_path = sig_path
        self.output_dir = output_dir
        self.coords = coords
        self.is_running = True

    def run(self):
        count = len(self.files)
        success_count = 0
        errors = []
        
        # Coordenadas por defecto si no se definieron visualmente
        final_x, final_y = 400, 700
        final_w, final_h = 150, 60
        
        if self.coords:
            final_x, final_y, final_w, final_h = self.coords

        for i, pdf_path in enumerate(self.files):
            if not self.is_running: break

            file_name = os.path.basename(pdf_path)
            
            # Avisar que estamos trabajando en este archivo
            self.status_updated.emit(f"Procesando ({i+1}/{count}): {file_name}")
            
            # Determinar ruta de salida
            target_dir = self.output_dir if self.output_dir else os.path.dirname(pdf_path)
            output_path = os.path.join(target_dir, f"SIGNED_{file_name}")
            
            # --- INTENTAR FIRMAR ---
            ok, msg = PDFStamper.stamp_pdf(
                pdf_path, self.sig_path, output_path,
                x=final_x, y=final_y, width=final_w, height=final_h
            )
            
            if ok:
                success_count += 1
                short_msg = "Firmado OK"
            else:
                errors.append(f"{file_name}: {msg}")
                short_msg = msg # El mensaje técnico del error
            
            # --- NOTIFICAR RESULTADO INDIVIDUAL ---
            # Esto dispara la actualización visual en la lista (Check verde o X roja)
            self.file_processed.emit(i, ok, short_msg)
            
            # Actualizar barra de progreso
            percent = int(((i + 1) / count) * 100)
            self.progress_updated.emit(percent)

        # Generar reporte final
        final_msg = f"Proceso finalizado.\n\n"
        final_msg += f"✅ Correctos: {success_count}\n"
        final_msg += f"❌ Fallidos: {len(errors)}\n"
        
        if errors:
            final_msg += "\nPasa el mouse sobre los archivos en rojo para ver el error."
            
        self.finished_signal.emit(final_msg)
    
    def stop(self):
        self.is_running = False