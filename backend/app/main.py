"""
HobbyTrack FastAPI Backend - Main Application
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from typing import Dict, Any
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown events."""
    # Startup
    logger.info("HobbyTrack API starting up...")
    yield
    # Shutdown
    logger.info("HobbyTrack API shutting down...")


# Create FastAPI application
app = FastAPI(
    title="HobbyTrack API",
    description="Modern API wrapper for Trac legacy system",
    version="0.1.0",
    lifespan=lifespan
)

# Configure CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins since we're serving from same container
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for serving Vite-built frontend
static_dir = "/app/static"
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def serve_spa():
    """Serve the React SPA index.html at root."""
    index_file = "/app/static/index.html"
    if os.path.exists(index_file):
        return FileResponse(index_file)
    # Fallback if static files not found (development mode)
    return {"message": "HobbyTrack API is running", "version": "0.1.0"}


@app.get("/api/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "hobbytrack-api"}


@app.get("/api/test-trac")
async def test_trac_integration() -> Dict[str, Any]:
    """Test endpoint to verify Trac legacy integration."""
    try:
        # TODO: Import and test Trac environment
        # from trac.env import Environment
        # env = Environment(path_to_trac_project)
        
        return {
            "status": "success",
            "message": "Trac integration test endpoint",
            "trac_available": False,  # Will be True when integrated
            "ticket_count": 0  # Placeholder for actual ticket count
        }
    except Exception as e:
        logger.error(f"Trac integration test failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Trac integration error: {str(e)}"
        )


# SPA Fallback - catch all non-API routes and serve index.html
@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """
    Catch-all route for SPA fallback routing.
    Serves index.html for all non-API routes to enable client-side routing.
    """
    # Don't interfere with API routes
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
    
    # Serve index.html for all other routes (SPA routing)
    index_file = "/app/static/index.html"
    if os.path.exists(index_file):
        return FileResponse(index_file)
    
    # Fallback if static files not available
    raise HTTPException(status_code=404, detail="Application not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True) 