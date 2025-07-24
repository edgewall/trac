# HobbyTrack

Modern project tracking for hobbyists - a modernized version of the Trac project management system.

## Overview

HobbyTrack is a simple, visual, and motivating project tracker designed for individuals. It transforms the powerful Trac project management engine into a modern, user-friendly application that hobbyists can use to track their personal projects.

## Features

- **One-Click Setup**: Get up and running with a single `docker-compose up` command
- **Modern UI**: Clean, responsive React TypeScript frontend
- **Visual Kanban Boards**: Drag-and-drop task management
- **File Uploads**: Attach images and documents to tasks
- **Personal Dashboard**: Track progress and celebrate accomplishments
- **Project Templates**: Quick start with hobby-specific templates
- **OAuth Integration**: Sign in with Google or GitHub

## Architecture

- **Frontend**: React + TypeScript + Tailwind CSS
- **Backend**: FastAPI (Python) wrapping legacy Trac functionality
- **Database**: SQLite (local-first approach)
- **Deployment**: Docker Compose for easy setup

## Quick Start

1. Clone this repository
2. Run the application:
   ```bash
   docker-compose up
   ```
3. Open your browser to `http://localhost:3000`

The backend API will be available at `http://localhost:8000`

## Development

### Backend (FastAPI)
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend (React)
```bash
cd frontend
npm install
npm start
```

## Project Structure

```
/hobbytrack
├── backend/           # FastAPI application
│   ├── app/          # Main application code
│   ├── Dockerfile    # Backend container
│   └── requirements.txt
├── frontend/         # React TypeScript application
│   ├── src/         # Source code
│   ├── public/      # Static assets
│   ├── Dockerfile   # Frontend container
│   └── package.json
├── trac-legacy/     # Legacy Trac codebase (imported)
├── docker-compose.yml # One-click deployment
└── README.md
```

## Contributing

This project follows a 6-day implementation plan as outlined in the Product Requirements Document. See `.taskmaster/docs/prd.txt` for detailed specifications.

## License

This project builds upon the Trac project management system and respects its original licensing. 