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

# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health_check() -> dict[str, str]:
    """Returns service health status."""
    return {"status": "ok", "version": "0.1.0", "service": "Plum HQ Claims API"}


from fastapi import File, UploadFile, Form, HTTPException
from fastapi.responses import StreamingResponse
from backend.db.database import get_db
from sqlalchemy.orm import Session
from backend.db.models import ClaimRecord
from fastapi import Depends
from backend.models.claim import ClaimCategory, ClaimSubmission, ClaimTrace

@router.get("/claims", response_model=list[dict[str, Any]])
async def get_claims(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """
    Returns claim records from the database.
    """
    records = db.query(ClaimRecord).order_by(ClaimRecord.submitted_at.desc()).all()
    from backend.policy.loader import get_policy
    policy = get_policy()
    
    results = []
    for r in records:
        member = policy.get_member(r.member_id)
        name = member.name if member else "Unknown"
        results.append({
            "claim_id": r.claim_id,
            "member_id": r.member_id,
            "member_name": name,
            "claim_category": r.claim_category,
            "claimed_amount": r.claimed_amount,
            "approved_amount": r.approved_amount,
            "decision": r.decision,
            "status": r.status,
            "treatment_date": r.treatment_date,
            "submitted_at": r.submitted_at,
            "reasons": r.reasons
        })
    return results

@router.post("/claims/clear")
async def clear_claims(db: Session = Depends(get_db)):
    """Clears all claim records from the database for demo reset purposes."""
    deleted_count = db.query(ClaimRecord).delete()
    db.commit()
    return {"status": "success", "deleted_count": deleted_count}

@router.get("/claims/{claim_id}/trace")
async def get_claim_trace(claim_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Returns the complete trace for a claim.
    """
    record = db.query(ClaimRecord).filter(ClaimRecord.claim_id == claim_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Claim not found")
    if not record.trace:
        raise HTTPException(status_code=404, detail="Trace not found for this claim")
    return record.trace

from backend.orchestrator.pipeline import extract_claim_stream, process_claim_stream
from backend.models.claim import ClaimCategory
from typing import List
import uuid

@router.post("/claims/extract")
async def extract_claim(
    member_id: str = Form(...),
    claim_category: str = Form(...),
    files: List[UploadFile] = File(...)
):
    """
    Step 1: Parse the documents and return extracted details for review.
    Accepts one or more uploaded files; text from all of them is merged
    before being passed through the verification pipeline.
    """
    claim_id = f"CLM_{uuid.uuid4().hex[:8].upper()}"

    # Read every uploaded file into memory
    file_payloads = []
    for f in files:
        file_payloads.append({
            "file_bytes": await f.read(),
            "filename": f.filename,
            "content_type": f.content_type,
        })

    return StreamingResponse(
        extract_claim_stream(
            claim_id=claim_id,
            member_id=member_id,
            claim_category=claim_category,
            file_payloads=file_payloads,
        ),
        media_type="text/event-stream"
    )

from pydantic import BaseModel
class ProcessClaimRequest(BaseModel):
    claim_id: str
    member_id: str
    claim_category: str
    treatment_date: str
    claimed_amount: float
    hospital_name: str | None = None
    extracted_text: str
    extracted_fields: dict = {}
    initial_trace: dict

@router.post("/claims/process")
async def process_claim(req: ProcessClaimRequest):
    """
    Step 2: Take the reviewed details and finalise the claim decision.
    """
    claim = ClaimSubmission(
        claim_id=req.claim_id,
        member_id=req.member_id,
        claim_category=ClaimCategory(req.claim_category),
        treatment_date=req.treatment_date,
        claimed_amount=req.claimed_amount,
        hospital_name=req.hospital_name,
        documents=[] # We aren't re-processing documents
    )
    
    return StreamingResponse(
        process_claim_stream(
            claim=claim,
            extracted_text=req.extracted_text,
            extracted_fields=req.extracted_fields,
            initial_trace_data=req.initial_trace
        ),
        media_type="text/event-stream"
    )


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

