"""
backend/api/routes/claims.py
Phase 1: /health endpoint and mock claims data for the dashboard.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter

from backend.models.claim import (
    ClaimCategory,
    ClaimStatus,
    ClaimSummary,
    DecisionEnum,
)

router = APIRouter()

# ── Helpers ───────────────────────────────────────────────────────────────────

MEMBER_NAMES: dict[str, str] = {
    "EMP001": "Rajesh Kumar",
    "EMP002": "Priya Singh",
    "EMP003": "Amit Verma",
    "EMP004": "Sneha Reddy",
    "EMP005": "Vikram Joshi",
    "EMP006": "Kavita Nair",
    "EMP007": "Suresh Patil",
    "EMP008": "Ravi Menon",
    "EMP009": "Anita Desai",
    "EMP010": "Deepak Shah",
}

_MOCK_CLAIMS: list[dict[str, Any]] = [
    {
        "claim_id": "CLM_A1B2C3D4",
        "member_id": "EMP001",
        "member_name": "Rajesh Kumar",
        "claim_category": ClaimCategory.CONSULTATION,
        "claimed_amount": 1500.0,
        "approved_amount": 1350.0,
        "decision": DecisionEnum.APPROVED,
        "status": ClaimStatus.COMPLETED,
        "treatment_date": "2024-10-15",
        "submitted_at": datetime(2024, 10, 20, 9, 30),
    },
    {
        "claim_id": "CLM_E5F6G7H8",
        "member_id": "EMP002",
        "member_name": "Priya Singh",
        "claim_category": ClaimCategory.PHARMACY,
        "claimed_amount": 2800.0,
        "approved_amount": 2800.0,
        "decision": DecisionEnum.APPROVED,
        "status": ClaimStatus.COMPLETED,
        "treatment_date": "2024-10-18",
        "submitted_at": datetime(2024, 10, 22, 11, 15),
    },
    {
        "claim_id": "CLM_I9J0K1L2",
        "member_id": "EMP003",
        "member_name": "Amit Verma",
        "claim_category": ClaimCategory.DIAGNOSTIC,
        "claimed_amount": 12000.0,
        "approved_amount": 6000.0,
        "decision": DecisionEnum.PARTIAL,
        "status": ClaimStatus.COMPLETED,
        "treatment_date": "2024-10-10",
        "submitted_at": datetime(2024, 10, 14, 14, 0),
    },
    {
        "claim_id": "CLM_M3N4O5P6",
        "member_id": "EMP004",
        "member_name": "Sneha Reddy",
        "claim_category": ClaimCategory.DENTAL,
        "claimed_amount": 8500.0,
        "approved_amount": 0.0,
        "decision": DecisionEnum.REJECTED,
        "status": ClaimStatus.COMPLETED,
        "treatment_date": "2024-10-05",
        "submitted_at": datetime(2024, 10, 8, 10, 45),
    },
    {
        "claim_id": "CLM_Q7R8S9T0",
        "member_id": "EMP005",
        "member_name": "Vikram Joshi",
        "claim_category": ClaimCategory.CONSULTATION,
        "claimed_amount": 3500.0,
        "approved_amount": None,
        "decision": DecisionEnum.MANUAL_REVIEW,
        "status": ClaimStatus.COMPLETED,
        "treatment_date": "2024-10-25",
        "submitted_at": datetime(2024, 10, 28, 16, 30),
    },
    {
        "claim_id": "CLM_U1V2W3X4",
        "member_id": "EMP006",
        "member_name": "Kavita Nair",
        "claim_category": ClaimCategory.VISION,
        "claimed_amount": 4200.0,
        "approved_amount": None,
        "decision": None,
        "status": ClaimStatus.PROCESSING,
        "treatment_date": "2024-10-29",
        "submitted_at": datetime(2024, 11, 1, 8, 0),
    },
    {
        "claim_id": "CLM_Y5Z6A7B8",
        "member_id": "EMP007",
        "member_name": "Suresh Patil",
        "claim_category": ClaimCategory.ALTERNATIVE_MEDICINE,
        "claimed_amount": 6000.0,
        "approved_amount": 6000.0,
        "decision": DecisionEnum.APPROVED,
        "status": ClaimStatus.COMPLETED,
        "treatment_date": "2024-09-20",
        "submitted_at": datetime(2024, 9, 25, 12, 0),
    },
    {
        "claim_id": "CLM_C9D0E1F2",
        "member_id": "EMP008",
        "member_name": "Ravi Menon",
        "claim_category": ClaimCategory.PHARMACY,
        "claimed_amount": 950.0,
        "approved_amount": None,
        "decision": None,
        "status": ClaimStatus.PENDING,
        "treatment_date": "2024-11-01",
        "submitted_at": datetime(2024, 11, 1, 17, 55),
    },
]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health_check() -> dict[str, str]:
    """Returns service health status."""
    return {"status": "ok", "version": "0.1.0", "service": "Plum HQ Claims API"}


@router.get("/claims/mock", response_model=list[ClaimSummary])
async def get_mock_claims() -> list[dict[str, Any]]:
    """
    Returns mock claim records for Phase 1 dashboard display.
    """
    return _MOCK_CLAIMS


from fastapi import File, UploadFile
from backend.extractors.tier1_local import extract_text
from backend.extractors.tier2_vision import extract_text_from_image
from backend.agents.document_verifier import verify_document

@router.post("/claims/verify-docs")
async def verify_docs(file: UploadFile = File(...)) -> dict[str, Any]:
    """Temporary endpoint for Phase 3 document verification."""
    file_bytes = await file.read()
    ext = file.filename.split(".")[-1].lower() if file.filename else ""
    
    try:
        # Route to Tier 1 or Tier 2 based on extension
        if ext in ["pdf", "docx", "doc", "txt"]:
            text = extract_text(file_bytes, file.filename)
        elif ext in ["jpg", "jpeg", "png", "webp"]:
            text = extract_text_from_image(file_bytes, file.content_type or "image/jpeg")
        else:
            return {"error": f"Unsupported file type: {ext}"}
            
        # Verify document using Qwen
        verification = verify_document(text)
        
        return {
            "status": "success",
            "filename": file.filename,
            "verification": verification.dict(),
            "extracted_text_preview": text[:500] + "..." if len(text) > 500 else text
        }
    except Exception as e:
        return {"error": str(e)}

