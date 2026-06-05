"""
backend/policy/loader.py
Loads and parses policy_terms.json into typed dataclasses.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional

# ── Path to the policy file ───────────────────────────────────────────────────
_POLICY_FILE = Path(__file__).resolve().parent.parent.parent / "instructions" / "policy_terms.json"


# ── Typed dataclasses ─────────────────────────────────────────────────────────

@dataclass
class OpdCategory:
    name: str
    covered: bool
    sub_limit: float
    copay_percent: float
    network_discount_percent: float = 0.0
    requires_prescription: bool = False
    requires_pre_auth: bool = False
    pre_auth_threshold: Optional[float] = None
    high_value_tests_requiring_pre_auth: list[str] = field(default_factory=list)
    branded_drug_copay_percent: float = 0.0
    generic_mandatory: bool = False
    requires_dental_report: bool = False
    covered_procedures: list[str] = field(default_factory=list)
    excluded_procedures: list[str] = field(default_factory=list)
    covered_items: list[str] = field(default_factory=list)
    excluded_items: list[str] = field(default_factory=list)
    requires_registered_practitioner: bool = False
    max_sessions_per_year: Optional[int] = None
    covered_systems: list[str] = field(default_factory=list)


@dataclass
class WaitingPeriods:
    initial_waiting_period_days: int
    pre_existing_conditions_days: int
    specific_conditions: dict[str, int]


@dataclass
class FraudThresholds:
    same_day_claims_limit: int
    monthly_claims_limit: int
    high_value_claim_threshold: float
    auto_manual_review_above: float
    fraud_score_manual_review_threshold: float


@dataclass
class MemberRecord:
    member_id: str
    name: str
    date_of_birth: str
    gender: str
    relationship: str
    join_date: Optional[str] = None
    dependents: list[str] = field(default_factory=list)
    primary_member_id: Optional[str] = None


@dataclass
class Coverage:
    sum_insured_per_employee: float
    annual_opd_limit: float
    per_claim_limit: float
    family_floater_enabled: bool
    family_floater_combined_limit: float
    covered_relationships: list[str]


@dataclass
class PolicyConfig:
    policy_id: str
    policy_name: str
    insurer: str
    renewal_status: str
    policy_start_date: str
    policy_end_date: str
    coverage: Coverage
    opd_categories: dict[str, OpdCategory]
    waiting_periods: WaitingPeriods
    exclusions: list[str]
    dental_exclusions: list[str]
    vision_exclusions: list[str]
    network_hospitals: list[str]
    submission_deadline_days: int
    minimum_claim_amount: float
    fraud_thresholds: FraudThresholds
    members: list[MemberRecord]
    document_requirements: dict[str, dict[str, list[str]]]

    def get_member(self, member_id: str) -> Optional[MemberRecord]:
        for m in self.members:
            if m.member_id == member_id:
                return m
        return None

    def is_active(self) -> bool:
        return self.renewal_status == "ACTIVE"

    def is_network_hospital(self, hospital_name: str) -> bool:
        if not hospital_name:
            return False
        hospital_lower = hospital_name.lower()
        return any(n.lower() in hospital_lower or hospital_lower in n.lower()
                   for n in self.network_hospitals)


# ── Loader ────────────────────────────────────────────────────────────────────

def _parse_opd_category(name: str, raw: dict[str, Any]) -> OpdCategory:
    return OpdCategory(
        name=name,
        covered=raw.get("covered", False),
        sub_limit=float(raw.get("sub_limit", 0)),
        copay_percent=float(raw.get("copay_percent", 0)),
        network_discount_percent=float(raw.get("network_discount_percent", 0)),
        requires_prescription=raw.get("requires_prescription", False),
        requires_pre_auth=raw.get("requires_pre_auth", False),
        pre_auth_threshold=raw.get("pre_auth_threshold"),
        high_value_tests_requiring_pre_auth=raw.get("high_value_tests_requiring_pre_auth", []),
        branded_drug_copay_percent=float(raw.get("branded_drug_copay_percent", 0)),
        generic_mandatory=raw.get("generic_mandatory", False),
        requires_dental_report=raw.get("requires_dental_report", False),
        covered_procedures=raw.get("covered_procedures", []),
        excluded_procedures=raw.get("excluded_procedures", []),
        covered_items=raw.get("covered_items", []),
        excluded_items=raw.get("excluded_items", []),
        requires_registered_practitioner=raw.get("requires_registered_practitioner", False),
        max_sessions_per_year=raw.get("max_sessions_per_year"),
        covered_systems=raw.get("covered_systems", []),
    )


def load_policy(path: Path = _POLICY_FILE) -> PolicyConfig:
    """Load and parse the policy_terms.json into a typed PolicyConfig."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    ph = raw["policy_holder"]
    cov = raw["coverage"]
    ff = cov.get("family_floater", {})

    coverage = Coverage(
        sum_insured_per_employee=float(cov["sum_insured_per_employee"]),
        annual_opd_limit=float(cov["annual_opd_limit"]),
        per_claim_limit=float(cov["per_claim_limit"]),
        family_floater_enabled=ff.get("enabled", False),
        family_floater_combined_limit=float(ff.get("combined_limit", 0)),
        covered_relationships=ff.get("covered_relationships", []),
    )

    opd_categories = {
        name: _parse_opd_category(name, cat_raw)
        for name, cat_raw in raw["opd_categories"].items()
    }

    wp = raw["waiting_periods"]
    waiting_periods = WaitingPeriods(
        initial_waiting_period_days=int(wp["initial_waiting_period_days"]),
        pre_existing_conditions_days=int(wp["pre_existing_conditions_days"]),
        specific_conditions={k: int(v) for k, v in wp.get("specific_conditions", {}).items()},
    )

    excl = raw.get("exclusions", {})
    ft = raw["fraud_thresholds"]
    fraud = FraudThresholds(
        same_day_claims_limit=int(ft["same_day_claims_limit"]),
        monthly_claims_limit=int(ft["monthly_claims_limit"]),
        high_value_claim_threshold=float(ft["high_value_claim_threshold"]),
        auto_manual_review_above=float(ft["auto_manual_review_above"]),
        fraud_score_manual_review_threshold=float(ft["fraud_score_manual_review_threshold"]),
    )

    members = [
        MemberRecord(
            member_id=m["member_id"],
            name=m["name"],
            date_of_birth=m["date_of_birth"],
            gender=m["gender"],
            relationship=m["relationship"],
            join_date=m.get("join_date"),
            dependents=m.get("dependents", []),
            primary_member_id=m.get("primary_member_id"),
        )
        for m in raw.get("members", [])
    ]

    return PolicyConfig(
        policy_id=raw["policy_id"],
        policy_name=raw["policy_name"],
        insurer=raw["insurer"],
        renewal_status=ph.get("renewal_status", "ACTIVE"),
        policy_start_date=ph["policy_start_date"],
        policy_end_date=ph["policy_end_date"],
        coverage=coverage,
        opd_categories=opd_categories,
        waiting_periods=waiting_periods,
        exclusions=excl.get("conditions", []),
        dental_exclusions=excl.get("dental_exclusions", []),
        vision_exclusions=excl.get("vision_exclusions", []),
        network_hospitals=raw.get("network_hospitals", []),
        submission_deadline_days=raw["submission_rules"]["deadline_days_from_treatment"],
        minimum_claim_amount=float(raw["submission_rules"]["minimum_claim_amount"]),
        fraud_thresholds=fraud,
        members=members,
        document_requirements=raw.get("document_requirements", {}),
    )


# ── Singleton ─────────────────────────────────────────────────────────────────
_policy: Optional[PolicyConfig] = None


def get_policy() -> PolicyConfig:
    """Return the cached PolicyConfig, loading it on first call."""
    global _policy
    if _policy is None:
        _policy = load_policy()
    return _policy
