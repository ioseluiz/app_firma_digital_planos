from PyQt6.QtCore import QThread, pyqtSignal
from app.utils.pdf_stamper import PDFStamper
import os

class SigningWorker(QThread):
    # Señales
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    finished_signal = pyqtSignal(str)
    file_processed = pyqtSignal(int, bool, str)

    def __init__(self, work_queue, sig_path, output_dir):
        super().__init__()
        # work_queue es una lista de dicts: [{'path':..., 'coords':..., 'list_index':...}]
        self.work_queue = work_queue 
        self.sig_path = sig_path
        self.output_dir = output_dir
        self.is_running = True

    def run(self):
        count = len(self.work_queue)
        success_count = 0
        errors = []
        
        for i, task in enumerate(self.work_queue):
            if not self.is_running: break

            pdf_path = task['path']
            specific_coords = task['coords'] # Coordenadas para ESTE archivo (o None)
            list_index = task['list_index']  # Índice original en la lista UI

            file_name = os.path.basename(pdf_path)
            self.status_updated.emit(f"Procesando: {file_name}")
            
            # Definir posición: Específica > Default
            if specific_coords:
                fx, fy, fw, fh = specific_coords
            else:
                fx, fy, fw, fh = 400, 700, 150, 60 # Default hardcoded de emergencia
            
            # Definir salida
            target_dir = self.output_dir if self.output_dir else os.path.dirname(pdf_path)
            output_path = os.path.join(target_dir, f"SIGNED_{file_name}")
            
            # --- FIRMAR ---
            ok, msg = PDFStamper.stamp_pdf(
                pdf_path, self.sig_path, output_path,
                x=fx, y=fy, width=fw, height=fh
            )
            
            if ok:
                success_count += 1
                short_msg = "Firmado OK"
            else:
                errors.append(f"{file_name}: {msg}")
                short_msg = msg
            
            # Notificar resultado individual usando el índice correcto de la lista
            self.file_processed.emit(list_index, ok, short_msg)
            
            # Actualizar barra de progreso
            percent = int(((i + 1) / count) * 100)
            self.progress_updated.emit(percent)

        # Reporte final
        final_msg = f"Proceso finalizado.\n\n"
        final_msg += f"✅ Correctos: {success_count}\n"
        final_msg += f"❌ Fallidos: {len(errors)}\n"
        
        if errors:
            final_msg += "\nPasa el mouse sobre los archivos en rojo para ver el error."
            
        self.finished_signal.emit(final_msg)
    
    def stop(self):
        self.is_running = False