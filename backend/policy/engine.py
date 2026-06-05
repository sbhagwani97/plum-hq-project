"""
backend/policy/engine.py
Deterministic rules engine for claims processing.
"""
from __future__ import annotations
from datetime import datetime, date
from backend.policy.loader import get_policy, PolicyConfig
from backend.models.claim import ClaimSubmission, ClaimDecision, DecisionEnum, ClaimCategory

class PolicyEngine:
    def __init__(self, policy: PolicyConfig = None):
        self.policy = policy or get_policy()

    def evaluate(self, claim: ClaimSubmission) -> ClaimDecision:
        # Check if active
        if not self.policy.is_active():
            return self._reject(claim, "Policy is not active")
            
        # Get category config
        cat_key = claim.claim_category.value.lower()
        if cat_key not in self.policy.opd_categories:
            return self._reject(claim, f"Category {cat_key} not covered by policy")
            
        cat_config = self.policy.opd_categories[cat_key]
        if not cat_config.covered:
            return self._reject(claim, f"Category {cat_key} is explicitly not covered")

        # Check hospital network
        is_network = self.policy.is_network_hospital(claim.hospital_name) if claim.hospital_name else False
        
        # Calculate copay
        copay_percent = cat_config.copay_percent
        if is_network and cat_config.network_discount_percent > 0:
            copay_percent = max(0, copay_percent - cat_config.network_discount_percent)
            
        amount_after_copay = claim.claimed_amount * (1 - copay_percent / 100.0)
        
        # Apply limits
        approved_amount = min(
            amount_after_copay, 
            cat_config.sub_limit, 
            self.policy.coverage.per_claim_limit
        )

        decision = DecisionEnum.APPROVED if approved_amount == claim.claimed_amount else DecisionEnum.PARTIAL
        if approved_amount <= 0:
            decision = DecisionEnum.REJECTED
            
        reasons = []
        if copay_percent > 0:
            reasons.append(f"Applied {copay_percent}% co-pay")
        if approved_amount < amount_after_copay:
            reasons.append("Applied policy limit (category sub-limit or per-claim limit)")
        if is_network:
            reasons.append("Network hospital discount applied")

        return ClaimDecision(
            claim_id=claim.claim_id,
            member_id=claim.member_id,
            claim_category=claim.claim_category,
            claimed_amount=claim.claimed_amount,
            decision=decision,
            approved_amount=approved_amount,
            confidence_score=1.0,
            reasons=reasons,
            adjustments=[]
        )

    def _reject(self, claim: ClaimSubmission, reason: str) -> ClaimDecision:
        return ClaimDecision(
            claim_id=claim.claim_id,
            member_id=claim.member_id,
            claim_category=claim.claim_category,
            claimed_amount=claim.claimed_amount,
            decision=DecisionEnum.REJECTED,
            approved_amount=0.0,
            confidence_score=1.0,
            reasons=[reason],
            adjustments=[]
        )
