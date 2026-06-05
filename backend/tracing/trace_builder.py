"""
backend/tracing/trace_builder.py
Utility to build ClaimTrace step by step during orchestration.
"""
import time
from contextlib import contextmanager
from typing import Any, Optional
from backend.models.claim import ClaimTrace, TraceEntry, AgentStatus

class TraceBuilder:
    def __init__(self, claim_id: str):
        self.trace = ClaimTrace(claim_id=claim_id)

    @contextmanager
    def span(self, agent_name: str, confidence_impact: float = 0.0):
        start_time = time.time()
        entry = TraceEntry(
            agent=agent_name,
            status=AgentStatus.SUCCESS,
            confidence_impact=confidence_impact
        )
        
        try:
            yield entry
            entry.status = AgentStatus.SUCCESS
        except Exception as e:
            entry.status = AgentStatus.FAILED
            entry.error = str(e)
            raise e
        finally:
            entry.duration_ms = int((time.time() - start_time) * 1000)
            self.trace.append(entry)
