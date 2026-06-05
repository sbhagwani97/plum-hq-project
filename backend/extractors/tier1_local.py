"""
backend/extractors/tier1_local.py
Local text extraction using LangChain Document Loaders.
"""
from __future__ import annotations
import tempfile
import os
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, TextLoader

def extract_text(file_bytes: bytes, filename: str) -> str:
    ext = filename.split(".")[-1].lower()
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
        
    try:
        if ext == "pdf":
            loader = PyPDFLoader(tmp_path)
        elif ext in ("docx", "doc"):
            loader = Docx2txtLoader(tmp_path)
        elif ext == "txt":
            # using utf-8 with fallback
            loader = TextLoader(tmp_path, encoding="utf-8")
        else:
            raise ValueError(f"Unsupported local text extraction format: {ext}")
            
        pages = loader.load()
        text = "\n".join([page.page_content for page in pages])
        return text.strip()
    except Exception as e:
        # Fallback if TextLoader fails due to encoding
        if ext == "txt":
            return file_bytes.decode("utf-8", errors="ignore").strip()
        raise e
    finally:
        os.remove(tmp_path)
