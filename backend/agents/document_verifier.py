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

def verify_document(text: str) -> DocumentVerificationResult:
    # Qwen model requested by user
    model_name = "Qwen/Qwen3.5-9B"
    
    prompt = f"""
You are a medical document verifier. Given the following extracted text from a document, classify it into one of these types:
- PRESCRIPTION
- HOSPITAL_BILL
- DIAGNOSTIC_REPORT
- PHARMACY_BILL
- OTHER

Also, extract key fields if present (e.g., Patient Name, Date, Total Amount, Doctor Name).

Return ONLY a valid JSON object in the exact following structure:
{{
  "document_type": "PRESCRIPTION",
  "key_fields": {{
    "Patient Name": "Rajesh Kumar",
    "Doctor Name": "Dr. Arun Sharma",
    "Date": "01-Nov-2024"
  }}
}}

Text to analyze:
{text[:3000]}
"""

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": "You are a strict JSON outputting bot."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
        max_tokens=500
    )
    
    try:
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"):
            content = content[7:-3]
        elif content.startswith("```"):
            content = content[3:-3]
            
        data = json.loads(content.strip())
        return DocumentVerificationResult(**data)
    except Exception as e:
        return DocumentVerificationResult(
            document_type="UNKNOWN",
            key_fields={"error": str(e), "raw": response.choices[0].message.content}
        )
