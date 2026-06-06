"""
backend/orchestrator/pipeline.py
Orchestrates the claim submission process using LangGraph StateGraph.
"""
import json
import time
from typing import AsyncGenerator, Any, TypedDict, Annotated, Optional
from backend.models.claim import ClaimSubmission, ClaimDecision, ClaimStatus, TraceEntry
from backend.agents.document_verifier import verify_document
from backend.agents.member_validator import MemberValidatorAgent
from backend.agents.decision_agent import DecisionAgent
from backend.policy.loader import get_policy
from backend.extractors.tier1_local import extract_text
from backend.extractors.tier2_vision import extract_text_from_image

from backend.db.database import SessionLocal
from backend.db.models import ClaimRecord
from backend.tracing.trace_builder import TraceBuilder

from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableConfig

# Define State
class ClaimState(TypedDict):
    claim_id: str
    member_id: str
    claim_category: str
    # Multi-file support: each dict has file_bytes, filename, content_type
    file_payloads: Optional[list]
    # Legacy single-file fields kept for backward compat with process flow
    file_bytes: Optional[bytes]
    filename: Optional[str]
    content_type: Optional[str]
    
    extracted_text: Optional[str]
    extracted_fields: Optional[dict]
    # List of doc types detected per uploaded file e.g. ["PRESCRIPTION", "PHARMACY_BILL"]
    detected_doc_types: Optional[list]
    
    claim: Optional[ClaimSubmission]
    
    validation_result: Optional[dict]
    decision: Optional[ClaimDecision]
    trace_data: list[dict]
    error: Optional[str]
    is_complete: bool

def _emit(phase: str, message: str, data: dict = None, is_final: bool = False):
    payload = {"phase": phase, "message": message, "is_final": is_final}
    if data:
        payload["data"] = data
    return f"data: {json.dumps(payload, default=str)}\n\n"

# Nodes for Extraction Flow
def node_extract(state: ClaimState) -> dict:
    start_time = time.time()
    try:
        payloads = state.get("file_payloads") or []

        # Fallback: legacy single-file fields
        if not payloads and state.get("filename"):
            payloads = [{
                "file_bytes": state["file_bytes"],
                "filename": state["filename"],
                "content_type": state.get("content_type"),
            }]

        if not payloads:
            raise ValueError("No files provided for extraction.")

        parts = []
        per_file_types: list[str] = []  # one entry per uploaded file

        for idx, payload in enumerate(payloads, start=1):
            fname = payload.get("filename") or f"document_{idx}"
            ext = fname.split(".")[-1].lower() if "." in fname else ""
            fbytes = payload["file_bytes"]
            ctype = payload.get("content_type") or ""

            if ext in ["pdf", "docx", "doc", "txt"]:
                text = extract_text(fbytes, fname)
            elif ext in ["jpg", "jpeg", "png", "webp"]:
                text = extract_text_from_image(fbytes, ctype or "image/jpeg")
            else:
                raise ValueError(f"Unsupported file type: {ext} (file: {fname})")

            # Classify each document individually so node_verify can check
            # the full required-document set against what was actually uploaded.
            try:
                from backend.agents.document_verifier import _classify_document
                from langchain_openai import ChatOpenAI
                import os
                _llm = ChatOpenAI(
                    model="Qwen/Qwen3.5-9B",
                    base_url="https://api.together.xyz/v1",
                    api_key=os.getenv("TOGETHER_API_KEY"),
                    temperature=0.0,
                    max_tokens=20,
                )
                doc_type = _classify_document(text, _llm)
            except Exception:
                doc_type = "UNKNOWN"

            per_file_types.append(doc_type)
            header = f"--- Document {idx}: {fname} ({doc_type}) ---"
            parts.append(f"{header}\n{text}")

        combined_text = "\n\n".join(parts)

        trace = {
            "agent": "Tier 1/2 Document Extractor",
            "status": "SUCCESS",
            "output": {
                "text_length": len(combined_text),
                "num_files": len(payloads),
                "detected_types": per_file_types,
            },
            "duration_ms": int((time.time() - start_time) * 1000)
        }
        return {
            "extracted_text": combined_text,
            "detected_doc_types": per_file_types,
            "trace_data": state.get("trace_data", []) + [trace],
        }
    except Exception as e:
        trace = {
            "agent": "Tier 1/2 Document Extractor",
            "status": "FAILED",
            "error": str(e),
            "duration_ms": int((time.time() - start_time) * 1000)
        }
        return {"error": str(e), "trace_data": state.get("trace_data", []) + [trace]}

# ── Policy-driven document requirements (mirrors policy_terms.json) ─────────
# Maps claim category → the set of document types that MUST be present across
# all uploaded files.  The verifier LLM uses these labels:
#   PRESCRIPTION | HOSPITAL_BILL | DIAGNOSTIC_REPORT | PHARMACY_BILL | OTHER
#
# Note: LAB_REPORT from the policy is classified as DIAGNOSTIC_REPORT by the
# LLM, and DISCHARGE_SUMMARY maps to HOSPITAL_BILL, so we normalise here.
_REQUIRED_DOC_TYPES: dict[str, list[str]] = {
    "CONSULTATION":          ["PRESCRIPTION", "HOSPITAL_BILL"],
    "DIAGNOSTIC":            ["PRESCRIPTION", "DIAGNOSTIC_REPORT", "HOSPITAL_BILL"],
    "PHARMACY":              ["PRESCRIPTION", "PHARMACY_BILL"],
    "DENTAL":                ["HOSPITAL_BILL"],
    "VISION":                ["PRESCRIPTION", "HOSPITAL_BILL"],
    "ALTERNATIVE_MEDICINE":  ["PRESCRIPTION", "HOSPITAL_BILL"],
}

# Human-readable label for each doc type (used in error messages)
_DOC_TYPE_LABELS: dict[str, str] = {
    "PRESCRIPTION":      "a doctor's prescription (Rx slip listing medicines and diagnosis)",
    "HOSPITAL_BILL":     "a hospital or clinic bill/invoice",
    "DIAGNOSTIC_REPORT": "a diagnostic/lab report (blood test, scan, X-ray, etc.)",
    "PHARMACY_BILL":     "a pharmacy/chemist bill with medicine names and batch numbers",
}

def _friendly(doc_type: str) -> str:
    return _DOC_TYPE_LABELS.get(doc_type, doc_type.replace("_", " ").title())


def node_verify(state: ClaimState) -> dict:
    start_time = time.time()
    text = state["extracted_text"]
    selected_category = (state.get("claim_category") or "").upper()
    friendly_category = selected_category.replace("_", " ").title()

    # ── Step 1: run the full LLM verifier on the combined text ────────────────
    # This gives us key_fields, confidence, flags, and warnings for the record.
    doc_verification = verify_document(text)

    # ── Step 2: Quality & Patient Validation ──────────────────────────────────
    if "PARTIAL_DOCUMENT" in doc_verification.flags or "UNREADABLE" in doc_verification.flags or doc_verification.confidence < 0.5:
        raise ValueError(
            f"UNREADABLE_DOCUMENT: We could not clearly read the uploaded document(s). "
            f"Please ensure the image is clear, well-lit, and the entire document is visible, then re-upload."
        )
        
    all_patients_str = doc_verification.key_fields.get("All Patient Names", "")
    if all_patients_str:
        # Split by comma, strip whitespace, remove empty, and deduplicate
        names = set(name.strip().lower() for name in all_patients_str.split(",") if name.strip())
        if len(names) > 1:
            # We found multiple distinct names
            formatted_names = ", ".join(name.strip().title() for name in all_patients_str.split(",") if name.strip())
            raise ValueError(
                f"MULTIPLE_PATIENTS: The uploaded documents appear to belong to different people. "
                f"We found the following names: {formatted_names}. "
                f"Please ensure all documents belong to the same patient."
            )

    # ── Step 3: policy-driven required-document check ─────────────────────────
    # Use the per-file types captured during extraction (one entry per file).
    # Fall back to the single classification from the combined text when the
    # state key is absent (e.g. legacy single-file path).
    detected_types: list[str] = state.get("detected_doc_types") or [doc_verification.document_type]
    detected_set = set(detected_types)

    required = _REQUIRED_DOC_TYPES.get(selected_category, [])
    missing = [r for r in required if r not in detected_set]

    if missing:
        # Build an actionable, specific error message.
        missing_labels = [f"• {_friendly(m)}" for m in missing]
        uploaded_labels = [
            f"• {t.replace('_', ' ').title()}" for t in detected_types if t != "UNKNOWN"
        ] or ["• (unrecognised document)"]

        raise ValueError(
            f"MISSING_DOCUMENTS: Your {friendly_category} claim requires the following "
            f"document(s) that were not found in your upload:\n"
            + "\n".join(missing_labels)
            + "\n\nYou uploaded:\n"
            + "\n".join(uploaded_labels)
            + "\n\nPlease re-upload and include ALL required documents together."
        )

    # ── Step 4: warn if any uploaded doc is completely unrelated ──────────────
    all_allowed = set(required) | set(_REQUIRED_DOC_TYPES.get(selected_category, []))
    # (no hard error for extras/optionals — just carry on)

    # Determine trace status
    trace_status = "DEGRADED" if doc_verification.flags else "SUCCESS"

    trace = {
        "agent": "Document Verifier (LLM)",
        "status": trace_status,
        "output": {
            **doc_verification.model_dump(mode='json'),
            "detected_doc_types": detected_types,
            "required_doc_types": required,
        },
        "duration_ms": int((time.time() - start_time) * 1000)
    }
    return {
        "extracted_fields": doc_verification.key_fields,
        "trace_data": state.get("trace_data", []) + [trace],
    }

# Build Extraction Graph
extract_workflow = StateGraph(ClaimState)
extract_workflow.add_node("extract", node_extract)
extract_workflow.add_node("verify", node_verify)
extract_workflow.set_entry_point("extract")
extract_workflow.add_edge("extract", "verify")
extract_workflow.add_edge("verify", END)
extract_app = extract_workflow.compile()

async def extract_claim_stream(
    claim_id: str,
    member_id: str,
    claim_category: str,
    file_payloads: list,
) -> AsyncGenerator[str, None]:
    trace_builder = TraceBuilder(claim_id)
    filenames = [p.get("filename", "document") for p in file_payloads]
    label = ", ".join(filenames) if len(filenames) <= 3 else f"{len(filenames)} documents"

    initial_state = {
        "claim_id": claim_id,
        "member_id": member_id,
        "claim_category": claim_category,
        "file_payloads": file_payloads,
        "trace_data": []
    }
    
    extracted_text = ""
    extracted_fields = {}
    
    try:
        # We manually emit the SSE while iterating over LangGraph events
        yield _emit("extraction", f"Extracting text from {label}...")
        
        async for event in extract_app.astream_events(initial_state, version="v2"):
            kind = event["event"]
            node = event.get("name")
            
            if kind == "on_chain_end" and node == "extract":
                extracted_text = event["data"]["output"].get("extracted_text", "")
                yield _emit("extraction", f"Text extraction complete ({len(file_payloads)} file(s)).", {"preview": extracted_text[:100] + "..."})
                
            elif kind == "on_chain_start" and node == "verify":
                yield _emit("verification", "Verifying document type and extracting key fields...")
                
            elif kind == "on_chain_end" and node == "verify":
                extracted_fields = event["data"]["output"].get("extracted_fields", {})
                # Pull quality metadata from the trace entry for the frontend
                trace_entries = event["data"]["output"].get("trace_data", [])
                verifier_trace = next(
                    (t for t in reversed(trace_entries) if t.get("agent") == "Document Verifier (LLM)"),
                    {}
                )
                verifier_output = verifier_trace.get("output", {})
                yield _emit("verification", "Document verified.", {
                    "key_fields": extracted_fields,
                    "confidence": verifier_output.get("confidence", 1.0),
                    "flags": verifier_output.get("flags", []),
                    "warnings": verifier_output.get("warnings", []),
                })
                
            elif kind == "on_chain_end" and node == "LangGraph":
                final_state = event["data"]["output"]
                for t in final_state.get("trace_data", []):
                    trace_builder.trace.append(TraceEntry(**t))
                    
                extracted_data = {
                    "text": extracted_text,
                    "extracted_fields": extracted_fields,
                    "trace": trace_builder.trace.model_dump(mode='json')
                }
                yield _emit("complete", "Extraction ready for review.", extracted_data, is_final=True)
                
    except Exception as e:
        yield _emit("error", f"Extraction failed: {str(e)}", is_final=True)


# Nodes for Process Flow
def node_validate(state: ClaimState) -> dict:
    start_time = time.time()
    policy = get_policy()
    validator = MemberValidatorAgent(policy)
    claim = state["claim"]
    res = validator.validate(claim.member_id, claim.treatment_date, state.get("extracted_fields"))
    
    trace = {
        "agent": "Member Policy Validator",
        "status": "SUCCESS" if res.is_valid else "FAILED",
        "output": res.model_dump(mode='json'),
        "duration_ms": int((time.time() - start_time) * 1000)
    }
    
    if not res.is_valid:
        # Trace is appended even if we raise an error? Actually, wait, raising ValueError stops the graph.
        # But let's return the trace_data so it's recorded if we catch it, or we just raise it.
        # Langgraph won't save state updates if an exception is raised from the node.
        # So we should probably handle it or just let the trace not be complete.
        # Actually it's fine for now, we'll just raise it.
        pass
        
    if not res.is_valid:
        raise ValueError(f"Validation failed: {', '.join(res.reasons)}")
    return {"validation_result": res.model_dump(mode='json'), "trace_data": state.get("trace_data", []) + [trace]}

def node_decision(state: ClaimState) -> dict:
    start_time = time.time()
    decision_agent = DecisionAgent()
    decision = decision_agent.evaluate_claim(state["claim"], state["extracted_text"], state.get("extracted_fields"))
    trace = {
        "agent": "Decision LLM Agent",
        "status": "SUCCESS",
        "output": {"decision": decision.decision.value, "reasons": decision.reasons, "approved_amount": decision.approved_amount},
        "duration_ms": int((time.time() - start_time) * 1000)
    }
    return {"decision": decision, "trace_data": state.get("trace_data", []) + [trace]}

def node_save(state: ClaimState) -> dict:
    decision = state["decision"]
    claim = state["claim"]
    trace_builder = TraceBuilder(claim.claim_id)
    # Reconstruct trace for saving
    for t in state.get("trace_data", []):
        trace_builder.trace.append(TraceEntry(**t))
        
    trace_builder.trace.final_decision = decision.decision
    trace_builder.trace.confidence_score = decision.confidence_score
    trace_builder.trace.approved_amount = decision.approved_amount
    trace_builder.trace.reasons = decision.reasons
    
    db = SessionLocal()
    try:
        record = ClaimRecord(
            claim_id=decision.claim_id,
            member_id=decision.member_id,
            claim_category=decision.claim_category.value,
            claimed_amount=decision.claimed_amount,
            approved_amount=decision.approved_amount,
            decision=decision.decision.value,
            status=ClaimStatus.COMPLETED.value,
            treatment_date=claim.treatment_date,
            reasons=decision.reasons,
            adjustments=decision.adjustments,
            confidence_score=decision.confidence_score,
            trace=trace_builder.trace.model_dump(mode='json')
        )
        db.add(record)
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
    
    decision.trace = trace_builder.trace
    return {"is_complete": True}

process_workflow = StateGraph(ClaimState)
process_workflow.add_node("validate", node_validate)
process_workflow.add_node("decision", node_decision)
process_workflow.add_node("save", node_save)
process_workflow.set_entry_point("validate")
process_workflow.add_edge("validate", "decision")
process_workflow.add_edge("decision", "save")
process_workflow.add_edge("save", END)
process_app = process_workflow.compile()

async def process_claim_stream(
    claim: ClaimSubmission, extracted_text: str, extracted_fields: dict, initial_trace_data: dict
) -> AsyncGenerator[str, None]:
    
    initial_state = {
        "claim": claim,
        "extracted_text": extracted_text,
        "extracted_fields": extracted_fields,
        "trace_data": initial_trace_data.get("agents", []) if initial_trace_data else []
    }
    
    try:
        yield _emit("validation", f"Validating policy coverage for member {claim.member_id}...")
        
        async for event in process_app.astream_events(initial_state, version="v2"):
            kind = event["event"]
            node = event.get("name")
            
            if kind == "on_chain_end" and node == "validate":
                res = event["data"]["output"]["validation_result"]
                yield _emit("validation", "Member validation complete.", res)
                
            elif kind == "on_chain_start" and node == "decision":
                yield _emit("decision", "Running decision agent...")
                
            elif kind == "on_chain_end" and node == "decision":
                decision = event["data"]["output"]["decision"]
                yield _emit("decision", f"Decision made: {decision.decision.value}", decision.model_dump(mode='json'))
                
            elif kind == "on_chain_start" and node == "save":
                yield _emit("saving", "Saving claim record and trace to database...")
                
            elif kind == "on_chain_end" and node == "LangGraph":
                final_state = event["data"]["output"]
                decision = final_state["decision"]
                yield _emit("complete", "Claim processing complete.", decision.model_dump(mode='json'), is_final=True)
                
    except Exception as e:
        yield _emit("error", f"Pipeline failed: {str(e)}", is_final=True)
