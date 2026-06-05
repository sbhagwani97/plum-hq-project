"""
backend/agents/document_verifier.py
Verifies the type and extracts key fields from the text of a document.
"""
from __future__ import annotations
import os
import json
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
client = OpenAI(api_key=TOGETHER_API_KEY, base_url="https://api.together.xyz/v1")

class DocumentVerificationResult(BaseModel):
    document_type: str
    key_fields: dict[str, str]

from langchain_openai import ChatOpenAI

def verify_document(text: str) -> DocumentVerificationResult:
    model_name = "google/gemma-3n-E4B-it"
    llm = ChatOpenAI(
        model=model_name, 
        base_url="https://api.together.xyz/v1", 
        api_key=TOGETHER_API_KEY, 
        temperature=0.1,
        max_tokens=500
    )
    
    structured_llm = llm.with_structured_output(DocumentVerificationResult)
    
    prompt = f"""
You are a medical document verifier. Given the following extracted text from a document, classify it into one of these types:
- PRESCRIPTION
- HOSPITAL_BILL
- DIAGNOSTIC_REPORT
- PHARMACY_BILL
- OTHER

Also, extract key fields if present (e.g., Patient Name, Date, Total Amount, Doctor Name).

Text to analyze:
{text}
"""
    try:
        return structured_llm.invoke(prompt)
    except Exception as e:
        return DocumentVerificationResult(
            document_type="UNKNOWN",
            key_fields={"error": str(e)}
        )

from langchain_core.tools import tool

@tool
def verify_document_tool(text: str) -> str:
    """Verifies the document type and extracts key fields from the raw text.
    Use this tool after extracting text to ensure it's the correct document type.
    """
    res = verify_document(text)
    return res.model_dump_json()
