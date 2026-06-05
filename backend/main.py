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
app.include_router(claims_router, prefix="/api", tags=["claims"])


# ── Frontend entrypoint ───────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_dashboard(request: Request) -> HTMLResponse:
    """Serve the main SPA dashboard."""
    return templates.TemplateResponse(request=request, name="index.html")
