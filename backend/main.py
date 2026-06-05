"""
backend/main.py
FastAPI application entrypoint for Plum HQ AI Claims Processing System.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from fastapi.responses import HTMLResponse

from backend.api.routes.claims import router as claims_router

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "frontend" / "static"
TEMPLATES_DIR = BASE_DIR / "frontend" / "templates"

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Plum HQ AI Claims Processing System",
    description="Multi-agent pipeline for health insurance claim processing.",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

import logging
import time
import json
from starlette.middleware.base import BaseHTTPMiddleware

logging.basicConfig(level=logging.INFO, format='%(message)s')

class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        logging.info(json.dumps({
            "event": "request_started",
            "method": request.method,
            "url": str(request.url),
            "client": request.client.host if request.client else None
        }))
        
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            status_code = 500
            logging.error(json.dumps({
                "event": "request_failed",
                "method": request.method,
                "url": str(request.url),
                "error": str(e)
            }))
            raise e
        finally:
            process_time = time.time() - start_time
            logging.info(json.dumps({
                "event": "request_finished",
                "method": request.method,
                "url": str(request.url),
                "status_code": status_code,
                "duration_ms": round(process_time * 1000, 2)
            }))
        
        return response

app.add_middleware(StructuredLoggingMiddleware)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ── Templates ─────────────────────────────────────────────────────────────────
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ── Routers ───────────────────────────────────────────────────────────────────
from backend.api.routes.policy import router as policy_router
app.include_router(claims_router, prefix="/api", tags=["claims"])
app.include_router(policy_router, prefix="/api/policy", tags=["policy"])


# ── Frontend entrypoint ───────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_dashboard(request: Request) -> HTMLResponse:
    """Serve the main SPA dashboard."""
    return templates.TemplateResponse(request=request, name="index.html")
