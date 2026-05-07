# Manim Agent Monorepo

Welcome to the Manim Agent project. This repository contains both the Backend AI Agent and the Frontend Dashboard.

## Project Structure

- `backend/`: Python FastAPI service, AI Orchestrator, and Celery Workers.
- `frontend/`: React + Vite + Tailwind dashboard for managing projects and scenes.

## Quick Start

### 1. Backend (AI Agent)
The backend manages the video production pipeline, from planning to rendering.
```bash
cd backend
make dev
```
See [backend/README.md](backend/README.md) for detailed setup.

### 2. Frontend (Dashboard)
The frontend provides a rich UI to control the Agent and visualize the rendering process.
```bash
cd frontend
npm install
npm run dev
```
See [frontend/README.md](frontend/README.md) for detailed setup.

## Development Workflow

1. Start the backend API and workers.
2. Start the frontend development server.
3. Use the **Guest Login** button on the login page for quick local testing.
4. Monitor Agent activity in real-time via the Scene Editor.

## License
MIT
