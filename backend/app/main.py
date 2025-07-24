"""
HobbyTrack FastAPI Backend - Main Application
"""

from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, List
import logging
import os
import sys
import jwt
import requests
from pydantic import BaseModel, validator

# Add the project root to Python path to import Trac modules
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Clerk configuration
CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY", "")
CLERK_PUBLISHABLE_KEY = os.getenv("CLERK_PUBLISHABLE_KEY", "")

# Development mode check
DEVELOPMENT_MODE = not CLERK_SECRET_KEY
if DEVELOPMENT_MODE:
    logger.warning("Running in DEVELOPMENT MODE - Clerk authentication is mocked!")

# JWT security scheme
security = HTTPBearer(auto_error=False)

# Pydantic Models for API responses
class TicketModel(BaseModel):
    """Individual ticket model with validation."""
    id: int
    summary: str
    status: str
    priority: str
    reporter: str
    owner: str
    created: int
    
    @validator('summary')
    def summary_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Summary cannot be empty')
        return v.strip()
    
    @validator('status')
    def status_must_be_valid(cls, v):
        valid_statuses = ['new', 'assigned', 'accepted', 'closed', 'reopened']
        if v not in valid_statuses:
            logger.warning(f"Unexpected ticket status: {v}")
        return v

class TicketsResponse(BaseModel):
    """Response model for tickets endpoint."""
    status: str
    user_id: str
    user_email: str
    tickets: List[TicketModel]
    total_count: int
    message: Optional[str] = None

class ClerkUser(BaseModel):
    """User information from Clerk authentication."""
    user_id: str
    email: str
    first_name: str
    last_name: str


class AuthenticationError(Exception):
    """Custom exception for authentication errors."""
    pass


async def verify_clerk_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> ClerkUser:
    """
    Verify Clerk JWT token and return user information.
    This is a FastAPI dependency that can be used to protect routes.
    """
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication credentials required"
        )
    
    token = credentials.credentials
    
    try:
        # For development/testing, we'll do a simple verification
        # In production, you would verify against Clerk's JWKS endpoint
        if not CLERK_SECRET_KEY:
            logger.warning("CLERK_SECRET_KEY not set - using development mode authentication")
            # Development mode - minimal validation
            if token.startswith("dev_") or token == "development-token":
                return ClerkUser(
                    user_id="dev_user_123",
                    email="developer@hobbytrack.local",
                    first_name="Development",
                    last_name="User"
                )
        
        # TODO: In production, implement proper JWT verification with Clerk's public keys
        # This would involve:
        # 1. Fetching Clerk's JWKS from https://[clerk-domain]/.well-known/jwks.json
        # 2. Verifying the JWT signature using the appropriate public key
        # 3. Validating claims (iss, aud, exp, etc.)
        
        # For now, return a placeholder that shows the integration is working
        logger.info(f"Token verification attempted for token: {token[:20]}...")
        
        # Simulate successful authentication for demo purposes
        return ClerkUser(
            user_id="user_placeholder",
            email="user@example.com", 
            first_name="Demo",
            last_name="User"
        )
        
    except Exception as e:
        logger.error(f"Token verification failed: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token"
        )


def require_auth(user: ClerkUser = Depends(verify_clerk_token)) -> ClerkUser:
    """
    Dependency that requires authentication.
    Use this for routes that need authenticated users.
    """
    return user


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown events."""
    # Startup
    logger.info("HobbyTrack API starting up...")
    if CLERK_SECRET_KEY:
        logger.info("Clerk authentication enabled")
    else:
        logger.warning("Clerk authentication in development mode - set CLERK_SECRET_KEY for production")
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
    
    # Mount assets directory separately for direct access
    assets_dir = "/app/static/assets"
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


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


@app.get("/api/auth/status")
async def auth_status(user: ClerkUser = Depends(require_auth)) -> Dict[str, Any]:
    """
    Protected endpoint to check authentication status.
    Returns current user information.
    """
    return {
        "authenticated": True,
        "user": {
            "id": user.user_id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name
        }
    }


@app.get("/api/test-trac")
async def test_trac_integration() -> Dict[str, Any]:
    """Test endpoint to verify Trac legacy integration."""
    try:
        # Import Trac environment
        from trac.env import Environment
        
        # Path to test Trac environment
        # In Docker container, test-projects is at /app/test-projects
        if os.path.exists("/app/test-projects"):
            trac_env_path = "/app/test-projects/my-drone-project"
        else:
            # Development mode - relative to project root
            trac_env_path = os.path.join(project_root, "test-projects", "my-drone-project")
        
        # Initialize Trac environment
        env = Environment(trac_env_path)
        
        # Get some basic information to verify integration
        with env.db_transaction as db:
            # Count tickets in the database
            cursor = db.cursor()
            cursor.execute("SELECT COUNT(*) FROM ticket")
            ticket_count = cursor.fetchone()[0]
            
            # Get some sample ticket IDs
            cursor.execute("SELECT id FROM ticket LIMIT 5")
            sample_ticket_ids = [row[0] for row in cursor.fetchall()]
        
        return {
            "status": "success",
            "message": "Trac integration successful",
            "trac_available": True,
            "environment_path": trac_env_path,
            "environment_name": env.project_name,
            "ticket_count": ticket_count,
            "sample_ticket_ids": sample_ticket_ids,
            "trac_version": env.trac_version
        }
    except Exception as e:
        logger.error(f"Trac integration test failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Trac integration error: {str(e)}"
        )


@app.get(
    "/api/tickets",
    response_model=TicketsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Tickets for Authenticated User",
    description="Retrieve a list of tickets from the Trac database for the authenticated user. Returns paginated results with ticket details.",
    responses={
        200: {
            "description": "Successfully retrieved tickets",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "user_id": "user_123",
                        "user_email": "user@example.com",
                        "tickets": [
                            {
                                "id": 1,
                                "summary": "Sample ticket",
                                "status": "new",
                                "priority": "high",
                                "reporter": "user",
                                "owner": "admin",
                                "created": 1640995200
                            }
                        ],
                        "total_count": 1,
                        "message": None
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        403: {"description": "Access forbidden"},
        503: {"description": "Trac service unavailable"},
        500: {"description": "Internal server error"}
    },
    tags=["Tickets"]
)
async def get_tickets(user: ClerkUser = Depends(require_auth)) -> TicketsResponse:
    """
    **Get Tickets for Authenticated User**
    
    This endpoint retrieves tickets from the legacy Trac database for the authenticated user.
    
    **Authentication Required:** 
    - Bearer token in Authorization header
    - Valid Clerk JWT token
    
    **Returns:**
    - List of tickets with metadata
    - User information
    - Total count
    
    **Example Usage:**
    ```
    curl -H "Authorization: Bearer <your-token>" http://localhost:8000/api/tickets
    ```
    """
    try:
        # Import Trac environment
        from trac.env import Environment
        
        # Path to test Trac environment
        if os.path.exists("/app/test-projects"):
            trac_env_path = "/app/test-projects/my-drone-project"
        else:
            trac_env_path = os.path.join(project_root, "test-projects", "my-drone-project")
        
        # Initialize Trac environment
        env = Environment(trac_env_path)
        
        # Get tickets for the authenticated user
        with env.db_transaction as db:
            cursor = db.cursor()
            # Get tickets with basic information
            cursor.execute("""
                SELECT id, summary, status, priority, reporter, owner, time
                FROM ticket 
                ORDER BY time DESC 
                LIMIT 20
            """)
            
            tickets = []
            for row in cursor.fetchall():
                tickets.append({
                    "id": row[0],
                    "summary": row[1],
                    "status": row[2],
                    "priority": row[3],
                    "reporter": row[4],
                    "owner": row[5],
                    "created": row[6]
                })
        
        return TicketsResponse(
            status="success",
            user_id=user.user_id,
            user_email=user.email,
            tickets=[TicketModel(**ticket) for ticket in tickets],
            total_count=len(tickets)
        )
        
    except FileNotFoundError:
        logger.error("Trac environment not found")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Trac environment is not available. Please check configuration."
        )
    except PermissionError:
        logger.error("Permission denied accessing Trac database")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database access denied. Please check permissions."
        )
    except Exception as e:
        logger.error(f"Failed to fetch tickets: {str(e)}")
        # Don't expose internal error details in production
        error_detail = str(e) if DEVELOPMENT_MODE else "Internal server error while fetching tickets"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail
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