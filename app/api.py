"""
FastAPI backend for the Weather-Advisory Support Bot.

Endpoints:
  POST /chat  {session_id, message} -> {reply, trace}
  POST /reset {session_id}
  GET  /health
  GET  /       serves the frontend
"""

from __future__ import annotations

from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path

from app.graph.build import run_turn, reset_session

app = FastAPI(
    title="Weather-Advisory Support Bot",
    description="Chat bot for outdoor activity safety using live weather data and SOPs.",
    version="1.0.0",
)

# --- Request/Response models ---

class ChatRequest(BaseModel):
    session_id: str
    message: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class ChatResponse(BaseModel):
    reply: str
    trace: dict

class ResetRequest(BaseModel):
    session_id: str

class HealthResponse(BaseModel):
    status: str


# --- Endpoints ---

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Process a chat message and return an advisory reply with trace."""
    try:
        user_coords = None
        if request.latitude is not None and request.longitude is not None:
            user_coords = {"latitude": request.latitude, "longitude": request.longitude}
        result = run_turn(request.session_id, request.message, user_coords=user_coords)
        return ChatResponse(reply=result["reply"], trace=result["trace"])
    except Exception as exc:
        import traceback
        print(f"[CHAT ERROR] {type(exc).__name__}: {exc}")
        traceback.print_exc()
        error_msg = str(exc)
        # Detect rate limit errors and return 429
        if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg or "RateLimit" in type(exc).__name__:
            raise HTTPException(
                status_code=429,
                detail="API rate limit exceeded. Please wait and try again.",
            )
        raise HTTPException(
            status_code=500,
            detail=f"Error processing message: {type(exc).__name__}: {exc}",
        )


@app.post("/reset")
async def reset(request: ResetRequest):
    """Reset a session's memory."""
    reset_session(request.session_id)
    return {"status": "ok", "session_id": request.session_id}


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse(status="ok")


# Serve frontend
_frontend_dir = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/")
async def serve_frontend():
    """Serve the frontend HTML page."""
    index_path = _frontend_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Frontend not found. Place index.html in frontend/ directory."}
