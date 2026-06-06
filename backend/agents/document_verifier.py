"""
backend/agents/document_verifier.py
Verifies the type and extracts key fields from the text of a document.

Approach (two-step):
  1. Classify — ask the LLM to identify the document type only.
  2. Extract  — send a second, type-specific prompt to pull the exact fields
                defined in sample_documents_guide.md for that doc type.

Post-extraction:
  - Doctor registration number regex validation (Indian state formats).
  - Confidence, flags, and warnings are surfaced for downstream agents.
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from openai import OpenAI
from pydantic import BaseModel, Field

load_dotenv()

TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
client = OpenAI(api_key=TOGETHER_API_KEY, base_url="https://api.together.xyz/v1")

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class DocumentVerificationResult(BaseModel):
    document_type: str
    key_fields: dict[str, str]
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Extraction confidence (0–1). Reduced when fields are missing or flagged.",
    )
    flags: list[str] = Field(
        default_factory=list,
        description=(
            "Machine-readable flags for downstream agents. Examples: "
            "INVALID_REG_NUMBER, MISSING_REG_NUMBER, DOCUMENT_ALTERATION, "
            "DUPLICATE_STAMP, MULTILINGUAL_CONTENT, PARTIAL_DOCUMENT."
        ),
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Human-readable notes about extraction quality or anomalies.",
    )


# ---------------------------------------------------------------------------
# Per-doc-type field extraction instructions (from sample_documents_guide.md)
# ---------------------------------------------------------------------------

_FIELD_INSTRUCTIONS: dict[str, str] = {
    "PRESCRIPTION": """
Extract the following fields from this medical prescription. Return a flat JSON object with these exact keys (use null if a field is absent):
- "Doctor Name"
- "Doctor Registration Number"   (e.g. KA/45678/2015)
- "Doctor Specialization"
- "Hospital / Clinic Name"
- "Hospital Address"
- "Patient Name"
- "All Patient Names" (comma-separated list of ALL distinct patient names found across the entire document text)
- "Patient Age"
- "Patient Gender"
- "Date"
- "Diagnosis"
- "Medicines"   (comma-separated, include dosage and duration, e.g. "Tab Paracetamol 650mg 1-1-1 x 5 days")
- "Tests Ordered"
""",
    "HOSPITAL_BILL": """
Extract the following fields from this hospital or clinic bill. Return a flat JSON object with these exact keys (use null if a field is absent):
- "Hospital Name"
- "Hospital Address"
- "GSTIN"
- "Bill Number"
- "Date"
- "Patient Name"
- "All Patient Names" (comma-separated list of ALL distinct patient names found across the entire document text)
- "Patient Age"
- "Patient Gender"
- "Line Items"   (comma-separated descriptions with amounts, e.g. "Room Rent 18000, Doctor Fee 2500")
- "Subtotal"
- "GST Amount"
- "Total Amount"
- "Payment Mode"
""",
    "DIAGNOSTIC_REPORT": """
Extract the following fields from this diagnostic / lab report. Return a flat JSON object with these exact keys (use null if a field is absent):
- "Lab Name"
- "NABL Accredited"   ("Yes" or "No")
- "Patient Name"
- "All Patient Names" (comma-separated list of ALL distinct patient names found across the entire document text)
- "Patient Age"
- "Patient Gender"
- "Referring Doctor"
- "Sample Date"
- "Report Date"
- "Sample ID"
- "Test Results"   (semicolon-separated, format: "Test Name: Result Unit [Normal Range]", e.g. "Hemoglobin: 13.2 g/dL [13.0-17.0]; WBC: 9800 /μL [4500-11000]")
- "Pathologist Name"
- "Pathologist Registration Number"
- "Remarks"
""",
    "PHARMACY_BILL": """
Extract the following fields from this pharmacy bill. Return a flat JSON object with these exact keys (use null if a field is absent):
- "Pharmacy Name"
- "Drug License Number"
- "Pharmacy Address"
- "Bill Number"
- "Date"
- "Patient Name"
- "All Patient Names" (comma-separated list of ALL distinct patient names found across the entire document text)
- "Prescribing Doctor"
- "Medicines"   (semicolon-separated, format: "Name Batch Exp Qty MRP Amt", e.g. "Paracetamol 650 A2341 03/26 15 2.50 37.50")
- "Subtotal"
- "Discount"
- "Net Amount"
""",
}

_GENERIC_FIELDS = """
Extract the following key fields from this medical document. Return a flat JSON object (use null if absent):
- "Patient Name"
- "All Patient Names" (comma-separated list of ALL distinct patient names found across the entire document text)
- "Date"
- "Doctor Name"
- "Total Amount"
- "Document Description"
"""


# ---------------------------------------------------------------------------
# Doctor registration number validation (Indian medical council formats)
# ---------------------------------------------------------------------------

# Covers: KA, MH, DL, TN, GJ, AP, UP, WB, KL (standard state councils)
# and Ayurveda national format: AYUR/<STATE>/<DIGITS>/<YEAR>
_REG_PATTERN = re.compile(
    r"\b(?:AYUR/[A-Z]{2}/\d{3,6}/\d{4}|(?:KA|MH|DL|TN|GJ|AP|UP|WB|KL)/\d{4,6}/\d{4})\b"
)


def validate_doctor_reg_number(reg_no: Optional[str]) -> tuple[bool, str]:
    """Return (is_valid, reason). `reg_no` may be None / empty."""
    if not reg_no:
        return False, "Registration number field is absent"
    if _REG_PATTERN.fullmatch(reg_no.strip()):
        return True, "Valid format"
    # Try a loose search in case the model returned surrounding text
    if _REG_PATTERN.search(reg_no):
        return True, "Valid format (embedded in text)"
    return False, f"Unrecognised format: '{reg_no}'"


# ---------------------------------------------------------------------------
# Step 1 — Classify
# ---------------------------------------------------------------------------

def _classify_document(text: str, llm: ChatOpenAI) -> str:
    """Return one of: PRESCRIPTION, HOSPITAL_BILL, DIAGNOSTIC_REPORT, PHARMACY_BILL, OTHER."""
    prompt = f"""You are a medical document classifier. Read the document below and return ONLY one of these labels — nothing else:
PRESCRIPTION
HOSPITAL_BILL
DIAGNOSTIC_REPORT
PHARMACY_BILL
OTHER

Rules:
- PRESCRIPTION   → doctor's Rx / treatment advice with medicines listed
- HOSPITAL_BILL  → invoice / receipt / bill from a hospital or clinic (including discharge summaries)
- DIAGNOSTIC_REPORT → lab report, pathology report, radiology / MRI / scan report
- PHARMACY_BILL  → pharmacy / chemist bill with medicine items, batch numbers, MRP
- OTHER          → anything else

Document:
{text}

Label:"""
    response = llm.invoke(prompt)
    raw = response.content.strip().upper().split()[0]
    valid = {"PRESCRIPTION", "HOSPITAL_BILL", "DIAGNOSTIC_REPORT", "PHARMACY_BILL", "OTHER"}
    return raw if raw in valid else "OTHER"


# ---------------------------------------------------------------------------
# Step 2 — Type-specific field extraction
# ---------------------------------------------------------------------------

def _extract_fields(text: str, doc_type: str, llm: ChatOpenAI) -> dict[str, str]:
    """Extract the guide-defined fields for the given doc type."""
    instructions = _FIELD_INSTRUCTIONS.get(doc_type, _GENERIC_FIELDS)
    prompt = f"""{instructions}

Return ONLY a valid JSON object. No markdown, no explanation.

Document:
{text}"""
    response = llm.invoke(prompt)
    raw = response.content.strip()
    # Strip any accidental markdown fences
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
    raw = re.sub(r"```$", "", raw).strip()
    try:
        parsed = json.loads(raw)
        # Flatten: keep only string values; convert None → remove key
        return {k: str(v) for k, v in parsed.items() if v is not None and str(v).strip() not in ("", "null", "None")}
    except json.JSONDecodeError:
        # Best-effort: return the raw text under a fallback key
        return {"_raw_extraction": raw[:500]}


# ---------------------------------------------------------------------------
# Anomaly detection (heuristic, no LLM needed)
# ---------------------------------------------------------------------------

_ALTERATION_HINTS = re.compile(
    r"\b(cancelled|corrected|crossed|overwritten|amended|altered)\b", re.IGNORECASE
)
_DUPLICATE_HINTS = re.compile(r"\b(DUPLICATE|COPY|TRIPLICATE)\b", re.IGNORECASE)
_REGIONAL_SCRIPT = re.compile(
    r"[\u0900-\u097F\u0B80-\u0BFF\u0C00-\u0C7F\u0980-\u09FF]"  # Devanagari, Tamil, Telugu, Bengali
)


def _detect_anomalies(text: str) -> tuple[list[str], list[str]]:
    """Return (flags, warnings) derived from heuristic text scanning."""
    flags: list[str] = []
    warnings: list[str] = []

    if _ALTERATION_HINTS.search(text):
        flags.append("DOCUMENT_ALTERATION")
        warnings.append("Document may contain corrections or alterations.")

    if _DUPLICATE_HINTS.search(text):
        flags.append("DUPLICATE_STAMP")
        warnings.append("Document is marked as DUPLICATE or COPY — surface to fraud detection.")

    if _REGIONAL_SCRIPT.search(text):
        flags.append("MULTILINGUAL_CONTENT")
        warnings.append("Regional language script detected. Non-English fields may be unextracted.")

    # Very short extracted text → likely partial / cut-off document
    if len(text.strip()) < 150:
        flags.append("PARTIAL_DOCUMENT")
        warnings.append("Extracted text is very short — document may be partial or cut off.")

    return flags, warnings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def verify_document(text: str) -> DocumentVerificationResult:
    """
    Two-step classify-then-extract with post-extraction validation.
    Populates confidence, flags, and warnings on the result.
    """
    llm = ChatOpenAI(
        model="Qwen/Qwen3.5-9B",
        base_url="https://api.together.xyz/v1",
        api_key=TOGETHER_API_KEY,
        temperature=0.0,
        max_tokens=600,
    )

    confidence = 1.0
    flags: list[str] = []
    warnings: list[str] = []

    # Step 1 — Classify
    try:
        doc_type = _classify_document(text, llm)
    except Exception as e:
        return DocumentVerificationResult(
            document_type="UNKNOWN",
            key_fields={"error": str(e)},
            confidence=0.0,
            flags=["CLASSIFICATION_FAILED"],
            warnings=[f"Classification LLM call failed: {e}"],
        )

    # Step 2 — Extract type-specific fields
    try:
        key_fields = _extract_fields(text, doc_type, llm)
    except Exception as e:
        key_fields = {"error": str(e)}
        confidence -= 0.3
        flags.append("EXTRACTION_FAILED")
        warnings.append(f"Field extraction LLM call failed: {e}")

    # Post-extraction: anomaly detection
    anomaly_flags, anomaly_warnings = _detect_anomalies(text)
    flags.extend(anomaly_flags)
    warnings.extend(anomaly_warnings)
    if anomaly_flags:
        confidence = max(0.1, confidence - 0.1 * len(anomaly_flags))

    # Post-extraction: doctor registration number validation (prescriptions only)
    if doc_type == "PRESCRIPTION":
        reg_no = key_fields.get("Doctor Registration Number")
        is_valid, reason = validate_doctor_reg_number(reg_no)
        if not is_valid:
            flag = "MISSING_REG_NUMBER" if not reg_no else "INVALID_REG_NUMBER"
            flags.append(flag)
            warnings.append(f"Doctor registration number issue — {reason}.")
            confidence = max(0.1, confidence - 0.15)

    return DocumentVerificationResult(
        document_type=doc_type,
        key_fields=key_fields,
        confidence=round(confidence, 2),
        flags=flags,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# LangChain tool wrapper
# ---------------------------------------------------------------------------

@tool
def verify_document_tool(text: str) -> str:
    """Verifies the document type and extracts key fields from the raw text.
    Use this tool after extracting text to ensure it's the correct document type.
    """
    res = verify_document(text)
    return res.model_dump_json()
