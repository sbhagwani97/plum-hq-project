"""
backend/models/claim.py
Core Pydantic models for the Plum HQ AI Claims Processing System.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
import uuid


# ── Enums ─────────────────────────────────────────────────────────────────────

class DecisionEnum(str, Enum):
    APPROVED = "APPROVED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class ClaimCategory(str, Enum):
    CONSULTATION = "CONSULTATION"
    DIAGNOSTIC = "DIAGNOSTIC"
    PHARMACY = "PHARMACY"
    DENTAL = "DENTAL"
    VISION = "VISION"
    ALTERNATIVE_MEDICINE = "ALTERNATIVE_MEDICINE"


class AgentStatus(str, Enum):
    SUCCESS = "SUCCESS"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ClaimStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


# ── Document Models ───────────────────────────────────────────────────────────

class DocumentInput(BaseModel):
    """A single uploaded document for a claim."""
    file_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    file_name: str
    file_path: str
    mime_type: str
    actual_type: Optional[str] = None  # e.g. PRESCRIPTION, HOSPITAL_BILL


# ── Claim Submission ──────────────────────────────────────────────────────────

class ClaimSubmission(BaseModel):
    """Input payload from the member submitting a claim."""
    claim_id: str = Field(default_factory=lambda: f"CLM_{uuid.uuid4().hex[:8].upper()}")
    member_id: str
    policy_id: str = "PLUM_GHI_2024"
    claim_category: ClaimCategory
    claimed_amount: float = Field(gt=0, description="Claimed amount in INR")
    treatment_date: str  # ISO 8601 date string: YYYY-MM-DD
    hospital_name: Optional[str] = None
    diagnosis: Optional[str] = None
    documents: list[DocumentInput] = Field(default_factory=list)
    submitted_at: datetime = Field(default_factory=datetime.utcnow)


# ── Trace Models ──────────────────────────────────────────────────────────────

class TraceEntry(BaseModel):
    """A single agent's execution record within the claim trace."""
    agent: str
    status: AgentStatus
    output: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    confidence_impact: float = 0.0  # positive = boost, negative = penalty
    duration_ms: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ClaimTrace(BaseModel):
    """Full audit trace for a claim, built incrementally by each agent."""
    claim_id: str
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    agents: list[TraceEntry] = Field(default_factory=list)
    final_decision: Optional[DecisionEnum] = None
    confidence_score: Optional[float] = None
    approved_amount: Optional[float] = None
    reasons: list[str] = Field(default_factory=list)

    def append(self, entry: TraceEntry) -> None:
        self.agents.append(entry)


# ── Decision Models ───────────────────────────────────────────────────────────

class ClaimDecision(BaseModel):
    """The final output of the claims processing pipeline."""
    claim_id: str
    member_id: str
    claim_category: ClaimCategory
    claimed_amount: float
    decision: DecisionEnum
    approved_amount: float
    confidence_score: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    adjustments: list[str] = Field(default_factory=list)
    trace: Optional[ClaimTrace] = None
    processed_at: datetime = Field(default_factory=datetime.utcnow)
    status: ClaimStatus = ClaimStatus.COMPLETED


# ── Mock / Summary Models ─────────────────────────────────────────────────────

class ClaimSummary(BaseModel):
    """Lightweight view of a claim for list/dashboard display."""
    claim_id: str
    member_id: str
    member_name: str
    claim_category: ClaimCategory
    claimed_amount: float
    approved_amount: Optional[float] = None
    decision: Optional[DecisionEnum] = None
    status: ClaimStatus
    treatment_date: str
    submitted_at: datetime
