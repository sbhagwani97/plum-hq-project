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

    def evaluate(self, claim: ClaimSubmission, extracted_text: str = "") -> ClaimDecision:
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

        # Check waiting periods
        member = self.policy.get_member(claim.member_id)
        if member and member.join_date:
            join_date = datetime.strptime(member.join_date, "%Y-%m-%d").date()
            treatment_date = datetime.strptime(claim.treatment_date, "%Y-%m-%d").date()
            days_since_join = (treatment_date - join_date).days
            
            if days_since_join < self.policy.waiting_periods.initial_waiting_period_days:
                return self._reject(claim, "WAITING_PERIOD: Initial waiting period not completed")
                
            text_lower = extracted_text.lower()
            for condition, days in self.policy.waiting_periods.specific_conditions.items():
                if condition.lower() in text_lower:
                    if days_since_join < days:
                        return self._reject(claim, f"WAITING_PERIOD: Waiting period for {condition} not completed. Eligible after {days} days from joining.")

        # Check Per-Claim Limit Outright Rejection (Only if sub_limit is not higher)
        limit = cat_config.sub_limit if cat_config.sub_limit > 0 and claim.claim_category.value != "CONSULTATION" else self.policy.coverage.per_claim_limit
        if claim.claimed_amount > limit and (cat_config.sub_limit == 0 or claim.claim_category.value == "CONSULTATION"):
            return self._reject(claim, f"PER_CLAIM_EXCEEDED: Claimed amount ({claim.claimed_amount}) exceeds per-claim limit of {self.policy.coverage.per_claim_limit}")

        # Check Pre-Auth
        if cat_config.requires_pre_auth and cat_config.pre_auth_threshold:
            if claim.claimed_amount >= cat_config.pre_auth_threshold:
                return self._reject(claim, "PRE_AUTH_MISSING: Pre-authorization required and missing for this amount. Please submit a pre-auth request.")

        # Check hospital network
        is_network = self.policy.is_network_hospital(claim.hospital_name) if claim.hospital_name else False
        
        # Calculate network discount and copay sequentially
        amount_after_discount = claim.claimed_amount
        if is_network and hasattr(cat_config, 'network_discount_percent') and cat_config.network_discount_percent > 0:
            amount_after_discount = claim.claimed_amount * (1 - cat_config.network_discount_percent / 100.0)
            
        amount_after_copay = amount_after_discount * (1 - cat_config.copay_percent / 100.0)
        
        # Apply limits
        limit = cat_config.sub_limit if cat_config.sub_limit > 0 and claim.claim_category.value != "CONSULTATION" else self.policy.coverage.per_claim_limit
        approved_amount = min(amount_after_copay, limit)

        if approved_amount < amount_after_copay:
            decision = DecisionEnum.PARTIAL
        else:
            decision = DecisionEnum.APPROVED
            
        if approved_amount <= 0:
            decision = DecisionEnum.REJECTED
            
        reasons = []
        if cat_config.copay_percent > 0:
            reasons.append(f"Applied {cat_config.copay_percent}% co-pay")
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
