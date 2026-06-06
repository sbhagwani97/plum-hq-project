"""
backend/agents/decision_agent.py
Combines deterministic policy engine with fuzzy LLM exclusion matching.
"""
from __future__ import annotations
import os
import json
from openai import OpenAI
from backend.policy.engine import PolicyEngine
from backend.models.claim import ClaimSubmission, ClaimDecision, DecisionEnum
import logging
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

class ExcludedItem(BaseModel):
    description: str
    amount: float
    reason: str

class ExclusionCheckResult(BaseModel):
    action: str = Field(description="Must be 'PROCEED', 'REJECT', or 'MANUAL_REVIEW'")
    reason: str
    excluded_items: list[ExcludedItem] = []

class DecisionAgent:
    def __init__(self):
        self.policy_engine = PolicyEngine()
        self.client = OpenAI(
            api_key=os.getenv("TOGETHER_API_KEY"), 
            base_url="https://api.together.xyz/v1"
        )
        
    def evaluate_claim(self, claim: ClaimSubmission, document_text: str, extracted_fields: dict = None) -> ClaimDecision:
        # 1. Deterministic Policy Check
        decision = self.policy_engine.evaluate(claim, document_text)
        
        # 2. Fuzzy LLM Exclusion Matching
        # Gather exclusions for this policy
        exclusions = self.policy_engine.policy.exclusions
        if claim.claim_category.value == "DENTAL":
            exclusions.extend(self.policy_engine.policy.dental_exclusions)
        elif claim.claim_category.value == "VISION":
            exclusions.extend(self.policy_engine.policy.vision_exclusions)
            
        if not exclusions:
            return decision

        # Deterministic fraud check (LLMs often ignore array length conditions)
        if len(claim.claims_history) >= self.policy_engine.policy.fraud_thresholds.same_day_claims_limit:
            decision.decision = DecisionEnum.MANUAL_REVIEW
            decision.reasons.append(f"Fraud Signal: Same-day claims limit exceeded ({len(claim.claims_history)} >= {self.policy_engine.policy.fraud_thresholds.same_day_claims_limit}).")
            return decision

        member = self.policy_engine.policy.get_member(claim.member_id)
        join_date = member.join_date if member else "Unknown"
        
        prompt = f"""
You are an AI medical claims assessor. Evaluate the claim against policy rules.
Output MUST be strictly valid JSON without markdown blocks.
Output must be concise. Do not explain your reasoning beyond the required `reason` field (max 15 words).

You must output a JSON object with this exact schema:
{{
  "action": "PROCEED" | "REJECT" | "MANUAL_REVIEW",
  "reason": "string (max 15 words)",
  "excluded_items": [
    {{ "description": "string", "amount": 0.0, "reason": "string" }}
  ]
}}

1. **Fraud**: Claims history count today: {len(claim.claims_history)}. Limit is {self.policy_engine.policy.fraud_thresholds.same_day_claims_limit}. If count >= limit, return action 'MANUAL_REVIEW'.
2. **Waiting Periods**: Member joined on {join_date}. Treatment date: {claim.treatment_date}. Specific condition waiting periods: {json.dumps(self.policy_engine.policy.waiting_periods.specific_conditions)}. If diagnosed treatment falls in a waiting period, return action 'REJECT'.
3. **Exclusions**: Check text against exclusions: {json.dumps(exclusions)}. If an exclusion applies to entire claim, return action 'REJECT'. If it applies to specific items, return action 'PROCEED' and list them in `excluded_items` with amounts. DO NOT hallucinate items.

Document Text:
{document_text}

Claim Category: {claim.claim_category.value}
Claimed Amount: {claim.claimed_amount}
"""

        try:
            llm = ChatOpenAI(
                model="google/gemma-3n-E4B-it",
                base_url="https://api.together.xyz/v1",
                api_key=self.client.api_key,
                temperature=0.2,
                max_tokens=300
            )
            
            response = llm.invoke(prompt)
            content = response.content.replace("```json", "").replace("```", "").strip()
            print(f"LLM Response: {content}")
            result_dict = json.loads(content)
            
            action = result_dict.get("action", "PROCEED")
            reason = result_dict.get("reason", "No reason provided")
            excluded_items = result_dict.get("excluded_items", [])
            
            if action == "MANUAL_REVIEW":
                decision.decision = DecisionEnum.MANUAL_REVIEW
                decision.reasons.append(f"LLM Flagged for Review: {reason}")
                
            elif excluded_items:
                total_excluded = sum(item.get("amount", 0.0) for item in excluded_items)
                for item in excluded_items:
                    decision.reasons.append(f"LLM Flagged Line-Item Exclusion: {item.get('description')} - {item.get('reason')} (-{item.get('amount')})")
                
                new_claimed = max(0.0, claim.claimed_amount - total_excluded)
                cat_config = self.policy_engine.policy.opd_categories.get(claim.claim_category.value.lower())
                copay_percent = cat_config.copay_percent if cat_config else 0
                network_discount = 0.0
                if claim.hospital_name in self.policy_engine.policy.network_hospitals and hasattr(cat_config, 'network_discount_percent'):
                    network_discount = cat_config.network_discount_percent
                
                new_after_discount = new_claimed * (1 - network_discount / 100.0)
                new_after_copay = new_after_discount * (1 - copay_percent / 100.0)
                
                limit = cat_config.sub_limit if cat_config and cat_config.sub_limit > 0 and claim.claim_category.value != "CONSULTATION" else self.policy_engine.policy.coverage.per_claim_limit
                
                decision.approved_amount = min(new_after_copay, limit)
                
                if decision.approved_amount <= 0:
                    decision.decision = DecisionEnum.REJECTED
                elif decision.decision == DecisionEnum.APPROVED:
                    decision.decision = DecisionEnum.PARTIAL
                
                decision.confidence_score = max(0.1, decision.confidence_score - 0.1)

            elif action == "REJECT":
                decision.decision = DecisionEnum.REJECTED
                decision.approved_amount = 0.0
                decision.reasons.append(f"LLM Rejected: {reason}")
                decision.confidence_score = max(0.1, decision.confidence_score - 0.1)
                
        except Exception as e:
            logging.error(f"LLM Exclusion check failed: {e}")
            # Do not block the claim if LLM fails, just note it in confidence/adjustments
            decision.confidence_score = max(0.1, decision.confidence_score - 0.2)
            decision.adjustments.append("LLM exclusion check failed to execute.")
            
        # 3. Bill Total Capping
        if extracted_fields:
            total_amount_str = extracted_fields.get("Total Amount")
            if total_amount_str:
                import re
                try:
                    cleaned = re.sub(r'[^\d.]', '', str(total_amount_str))
                    if cleaned:
                        extracted_total = float(cleaned)
                        if claim.claimed_amount > extracted_total:
                            if decision.approved_amount > extracted_total:
                                decision.approved_amount = extracted_total
                            decision.reasons.append(f"Claimed amount ({claim.claimed_amount}) exceeds documented bill total ({extracted_total}). Capped at bill total.")
                            if decision.decision == DecisionEnum.APPROVED:
                                decision.decision = DecisionEnum.PARTIAL
                except ValueError:
                    pass
                    
        return decision

from langchain_core.tools import tool

@tool
def evaluate_claim_tool(claim_json: str, extracted_text: str, extracted_fields_json: str = None) -> str:
    """Evaluates the claim against policy rules and exclusions using LLM.
    Args:
        claim_json: A JSON string of the ClaimSubmission object.
        extracted_text: The full extracted text from the medical documents.
        extracted_fields_json: A JSON string of the extracted fields.
    """
    import json
    claim_dict = json.loads(claim_json)
    claim = ClaimSubmission(**claim_dict)
    
    extracted_fields = None
    if extracted_fields_json:
        try:
            extracted_fields = json.loads(extracted_fields_json)
        except json.JSONDecodeError:
            pass
            
    agent = DecisionAgent()
    decision = agent.evaluate_claim(claim, extracted_text, extracted_fields)
    return decision.model_dump_json()
