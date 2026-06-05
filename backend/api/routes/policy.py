"""
backend/api/routes/policy.py
Phase 2: Member validation and policy endpoints.
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from backend.policy.loader import get_policy
from backend.agents.member_validator import MemberValidatorAgent, MemberValidationResult
from typing import Any

router = APIRouter()

@router.get("/members")
async def list_members() -> list[dict[str, Any]]:
    policy = get_policy()
    return [
        {
            "member_id": m.member_id,
            "name": m.name,
            "relationship": m.relationship,
            "dependents": m.dependents
        }
        for m in policy.members
    ]

@router.get("/coverage/{member_id}")
async def get_coverage(member_id: str, treatment_date: str = None) -> dict[str, Any]:
    policy = get_policy()
    member = policy.get_member(member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
        
    validator = MemberValidatorAgent(policy)
    validation = validator.validate(member_id, treatment_date)
    
    return {
        "member_id": member.member_id,
        "name": member.name,
        "relationship": member.relationship,
        "eligibility": validation.dict(),
        "policy_limits": {
            "sum_insured_per_employee": policy.coverage.sum_insured_per_employee,
            "annual_opd_limit": policy.coverage.annual_opd_limit,
            "per_claim_limit": policy.coverage.per_claim_limit,
        }
    }
