"""
backend/agents/member_validator.py
Agent to validate member eligibility and waiting periods.
"""
from __future__ import annotations
from datetime import datetime, date
from backend.policy.loader import get_policy, PolicyConfig
from pydantic import BaseModel
from typing import Optional

class MemberValidationResult(BaseModel):
    is_valid: bool
    member_id: str
    name: Optional[str] = None
    relationship: Optional[str] = None
    is_active: bool = False
    reasons: list[str] = []

class MemberValidatorAgent:
    def __init__(self, policy: PolicyConfig = None):
        self.policy = policy or get_policy()

    def validate(self, member_id: str, treatment_date_str: Optional[str] = None, extracted_fields: dict = None) -> MemberValidationResult:
        reasons = []
        member = self.policy.get_member(member_id)
        
        if not member:
            return MemberValidationResult(
                is_valid=False,
                member_id=member_id,
                reasons=["Member ID not found in policy"]
            )
            
        # Name Matching Check
        if extracted_fields:
            doc_name = extracted_fields.get("Patient Name") or extracted_fields.get("Patient") or extracted_fields.get("Name")
            if doc_name and member.name:
                # Basic normalization for matching (e.g. "Rajesh Kumar" vs "Kumar, Rajesh")
                def normalize(n):
                    return ''.join(c.lower() for c in n if c.isalnum())
                
                # Check if at least one word from the member name is in the doc name
                member_parts = [p.lower() for p in member.name.split()]
                doc_name_lower = doc_name.lower()
                
                # Simple heuristic: if none of the parts of the true member name are found in the doc name, flag it
                match_found = any(part in doc_name_lower for part in member_parts if len(part) > 2)
                
                # If it's a completely different name (e.g. member is "Rajesh Kumar", doc says "Amit Singh")
                if not match_found:
                    reasons.append(f"Name mismatch: Document is for '{doc_name}' but policy is for '{member.name}'")

        if treatment_date_str:
            try:
                treatment_date = datetime.strptime(treatment_date_str, "%Y-%m-%d").date()
                join_date = datetime.strptime(member.join_date, "%Y-%m-%d").date() if member.join_date else None
                policy_start = datetime.strptime(self.policy.policy_start_date, "%Y-%m-%d").date()
                policy_end = datetime.strptime(self.policy.policy_end_date, "%Y-%m-%d").date()
            except ValueError as e:
                return MemberValidationResult(
                    is_valid=False,
                    member_id=member_id,
                    name=member.name,
                    relationship=member.relationship,
                    reasons=[f"Date parsing error: {str(e)}"]
                )
                
            if not (policy_start <= treatment_date <= policy_end):
                reasons.append(f"Treatment date {treatment_date_str} is outside policy active period ({self.policy.policy_start_date} to {self.policy.policy_end_date})")
                
            if join_date:
                days_since_join = (treatment_date - join_date).days
                initial_wait = self.policy.waiting_periods.initial_waiting_period_days
                if days_since_join < initial_wait:
                    reasons.append(f"Member is within initial waiting period ({initial_wait} days). Joined on {member.join_date}")

        is_valid = len(reasons) == 0
        return MemberValidationResult(
            is_valid=is_valid,
            member_id=member.member_id,
            name=member.name,
            relationship=member.relationship,
            is_active=is_valid,
            reasons=reasons
        )

from langchain_core.tools import tool

@tool
def validate_member(member_id: str, treatment_date_str: str = None, extracted_fields_json: str = None) -> str:
    """Validates if a member is eligible for a claim based on policy rules.
    Args:
        member_id: The member's ID.
        treatment_date_str: Optional treatment date (YYYY-MM-DD).
        extracted_fields_json: Optional JSON string of extracted fields from the document.
    """
    import json
    extracted_fields = json.loads(extracted_fields_json) if extracted_fields_json else None
    validator = MemberValidatorAgent()
    result = validator.validate(member_id, treatment_date_str, extracted_fields)
    return result.model_dump_json()
