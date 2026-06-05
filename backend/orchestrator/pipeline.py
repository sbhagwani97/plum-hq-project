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

            header = f"--- Document {idx}: {fname} ---"
            parts.append(f"{header}\n{text}")

        combined_text = "\n\n".join(parts)

        trace = {
            "agent": "Tier 1/2 Document Extractor",
            "status": "SUCCESS",
            "output": {"text_length": len(combined_text), "num_files": len(payloads)},
            "duration_ms": int((time.time() - start_time) * 1000)
        }
        return {"extracted_text": combined_text, "trace_data": state.get("trace_data", []) + [trace]}
    except Exception as e:
        trace = {
            "agent": "Tier 1/2 Document Extractor",
            "status": "FAILED",
            "error": str(e),
            "duration_ms": int((time.time() - start_time) * 1000)
        }
        return {"error": str(e), "trace_data": state.get("trace_data", []) + [trace]}

# Mapping from claim category → accepted document types from the verifier LLM.
# HOSPITAL_BILL is accepted for CONSULTATION and DIAGNOSTIC because discharge
# summaries are classified as HOSPITAL_BILL and are commonly submitted for both.
_CATEGORY_TO_DOC_TYPES: dict[str, list[str]] = {
    "CONSULTATION":          ["PRESCRIPTION", "HOSPITAL_BILL"],
    "DIAGNOSTIC":            ["DIAGNOSTIC_REPORT", "HOSPITAL_BILL"],
    "PHARMACY":              ["PHARMACY_BILL", "PRESCRIPTION"],
    "DENTAL":                ["HOSPITAL_BILL"],
    "VISION":                ["HOSPITAL_BILL", "PRESCRIPTION"],
    "ALTERNATIVE_MEDICINE":  ["PRESCRIPTION", "HOSPITAL_BILL"],
}

def node_verify(state: ClaimState) -> dict:
    start_time = time.time()
    text = state["extracted_text"]
    doc_verification = verify_document(text)
    detected_type = doc_verification.document_type
    selected_category = (state.get("claim_category") or "").upper()

    # Category / document-type mismatch check
    allowed_types = _CATEGORY_TO_DOC_TYPES.get(selected_category, [])
    if allowed_types and detected_type not in allowed_types and detected_type != "UNKNOWN":
        friendly_category = selected_category.replace("_", " ").title()
        friendly_doc = detected_type.replace("_", " ").title()
        raise ValueError(
            f"CATEGORY_MISMATCH: You selected '{friendly_category}' but uploaded a '{friendly_doc}'. "
            f"Please upload the correct document type for your chosen claim category."
        )

    # Determine trace status — degrade if the verifier flagged quality issues
    trace_status = "DEGRADED" if doc_verification.flags else "SUCCESS"

    trace = {
        "agent": "Document Verifier (LLM)",
        "status": trace_status,
        "output": doc_verification.model_dump(mode='json'),
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
