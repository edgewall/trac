# Multi-stage Dockerfile for HobbyTrack
# Stage 1: Build frontend with Node.js and Vite

FROM node:18-alpine AS frontend-build

# Set working directory for frontend build
WORKDIR /app/frontend

# Copy package files for dependency installation
COPY frontend/package*.json ./

# Install dependencies (including optional platform-specific dependencies)
RUN npm ci --legacy-peer-deps

# Copy frontend source code
COPY frontend/ ./

# Build the Vite application for production
RUN npm run build

# Verify build output exists
RUN ls -la dist/

# Stage 2: Python runtime for FastAPI backend + static file serving
FROM python:3.11-slim AS production

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

# Copy backend requirements and install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source code
COPY backend/ .

# Copy built frontend static files from the Node.js build stage
COPY --from=frontend-build /app/frontend/dist ./static

# Create a directory for SQLite database
RUN mkdir -p /app/data

# Expose port 8000
EXPOSE 8000

# Run FastAPI with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"] 