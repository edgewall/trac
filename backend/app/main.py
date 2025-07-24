"""
HobbyTrack FastAPI Backend - Main Application
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import Dict, Any
import logging

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
    allow_origins=["http://localhost:3000"],  # React development server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def read_root() -> Dict[str, str]:
    """Root endpoint for health check."""
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True) 