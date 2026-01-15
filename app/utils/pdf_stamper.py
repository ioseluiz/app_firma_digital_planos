import fitz  # PyMuPDF
import os

class PDFStamper:
    @staticmethod
    def stamp_pdf(pdf_path, signature_img_path, output_path, page_num=0, x=400, y=700, width=150, height=60):
        doc = None
        try:
            doc = fitz.open(pdf_path)
            
            # Validación de página
            if page_num >= len(doc):
                page_num = len(doc) - 1
            
            page = doc[page_num]
            
            # Rotación
            page_rot = page.rotation
            
            # Coordenadas
            rect = fitz.Rect(x, y, x + width, y + height)
            
            # Insertar firma
            page.insert_image(
                rect, 
                filename=signature_img_path, 
                keep_proportion=True, 
                overlay=True,
                rotate=page_rot
            )
            
            # --- ESTRATEGIA DE GUARDADO ROBUSTO ---
            try:
                # INTENTO 1: Guardado Optimizado (Ideal para la mayoría)
                # deflate=True y clean=True intentan reducir el tamaño, 
                # pero causan el error "compression bomb" en mapas pesados.
                doc.save(output_path, garbage=4, deflate=True, clean=True)
            
            except Exception as e_save:
                # INTENTO 2: Guardado "Crudo" (Plan B)
                # Si falla la optimización, guardamos el archivo sin tocar sus streams internos.
                print(f"Advertencia: Guardado optimizado falló ({e_save}). Usando guardado simple.")
                doc.save(output_path)
            # --------------------------------------

            return True, "Firma aplicada correctamente."
            
        except Exception as e:
            return False, f"Error crítico: {str(e)}"
        finally:
            if doc:
                doc.close()