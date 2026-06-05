"""
backend/extractors/tier1_local.py
Local text extraction for PDFs and DOCX files.
"""
from __future__ import annotations
import fitz  # PyMuPDF
from io import BytesIO
import docx

def extract_text_from_pdf(file_bytes: bytes) -> str:
    text = ""
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            text += page.get_text() + "\n"
    return text.strip()

def extract_text_from_docx(file_bytes: bytes) -> str:
    doc = docx.Document(BytesIO(file_bytes))
    text = "\n".join([para.text for para in doc.paragraphs])
    return text.strip()

def extract_text(file_bytes: bytes, filename: str) -> str:
    ext = filename.split(".")[-1].lower()
    if ext == "pdf":
        return extract_text_from_pdf(file_bytes)
    elif ext in ("docx", "doc"):
        return extract_text_from_docx(file_bytes)
    elif ext == "txt":
        return file_bytes.decode("utf-8", errors="ignore")
    else:
        raise ValueError(f"Unsupported local text extraction format: {ext}")
