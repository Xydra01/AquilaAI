import os
import base64
import mimetypes
import fitz
import docx
import io

def process_local_attachments(file_paths):
    text_payloads = []
    image_payloads = []
    
    for path in file_paths:
        if not os.path.exists(path):
            continue
            
        file_name = os.path.basename(path)
        mime_type, _ = mimetypes.guess_type(path)
        
        with open(path, "rb") as f:
            file_bytes = f.read()
            
        # 1. Handle Images
        if mime_type and mime_type.startswith('image/'):
            base64_img = base64.b64encode(file_bytes).decode('utf-8')
            image_payloads.append(base64_img)
            
        # 2. Handle PDFs
        elif mime_type == 'application/pdf':
            try:
                doc = fitz.open(stream=file_bytes, filetype="pdf")
                extracted_text = ""
                for page in doc:
                    extracted_text += page.get_text()
                text_payloads.append(f"--- START FILE: {file_name} ---\n{extracted_text}\n--- END FILE ---")
            except Exception as e:
                text_payloads.append(f"[System: Could not parse PDF {file_name} - {str(e)}]")

        # 3. Handle Microsoft Word Documents (.docx)
        # 3. Handle Microsoft Word Documents (.docx)
        elif file_name.lower().endswith('.docx'):
            try:
                # Load the raw bytes into a virtual file, then parse it with docx
                doc = docx.Document(io.BytesIO(file_bytes))
                extracted_text_parts = []
                
                # Extract standard paragraphs
                for para in doc.paragraphs:
                    if para.text.strip():
                        extracted_text_parts.append(para.text.strip())
                        
                # Extract text from tables (Crucial for study guides/worksheets!)
                for table in doc.tables:
                    for row in table.rows:
                        row_data = []
                        for cell in row.cells:
                            if cell.text.strip() and cell.text.strip() not in row_data:
                                row_data.append(cell.text.strip())
                        if row_data:
                            extracted_text_parts.append(" | ".join(row_data))
                            
                extracted_text = "\n".join(extracted_text_parts)
                text_payloads.append(f"--- START FILE: {file_name} ---\n{extracted_text}\n--- END FILE ---")
            except Exception as e:
                text_payloads.append(f"[System: Could not parse DOCX {file_name} - {str(e)}]")
                
        # 4. Fallback for standard text/code files (.txt, .py, .md, etc.)
        else:
            try:
                decoded_text = file_bytes.decode('utf-8', errors='replace')
                text_payloads.append(f"--- START FILE: {file_name} ---\n{decoded_text}\n--- END FILE ---")
            except Exception:
                text_payloads.append(f"[System: Could not decode {file_name}]")

    max_chars = 90000 
    combined_text = "\n\n".join(text_payloads)
    text_chunks = []
    
    if combined_text.strip():
        for i in range(0, len(combined_text), max_chars):
            text_chunks.append(combined_text[i:i + max_chars])
            
    return text_chunks, image_payloads