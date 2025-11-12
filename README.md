# Dentist Appointment Scheduler

## Overview
This project implements the infrastructure for an AI-assisted dentist appointment scheduling service. The system is built with FastAPI and integrates with PostgreSQL, Redis, Google Calendar, and Slack. Orchestration will be handled using n8n. AI logic will be introduced in later phases; Phase 1 focuses on establishing the service pipeline and stubs for integrations.

## Architecture

- **Backend (`backend/`)**: FastAPI application exposing health, version, and Slack webhook endpoints.

- **Calendar Service (`calendar_service/`)**: Stub Google Calendar adapter for future integration.

- **Orchestrator (`orchestrator/`)**: n8n workflow templates coordinating event flows.

- **Infrastructure (`infra/`)**: Environment configuration, Alembic settings, and initial database schema.

- **Tests (`tests/`)**: Smoke tests ensuring primary endpoints respond as expected.

## Setup
1. Create and activate a Python 3.11 virtual environment.
2. Copy `infra/.env.example` to `.env` and update credentials.
3. Install dependencies:
   ```bash
   make setup
   ```
4. Initialize the database using `infra/init_db.sql` on PostgreSQL.

## Running the App
- Start the FastAPI server:
  ```bash
  make run
  ```
- Execute smoke tests:
  ```bash
  make test
  ```

## Dependencies
Key dependencies include:
- FastAPI, Uvicorn
- SQLAlchemy, psycopg
- Redis
- Pydantic, python-dotenv
- Pytest for testing

## Next Steps
- Implement real Google Calendar API logic with OAuth credentials.
- Add Slack event verification and user interaction handling.
- Expand database models and Alembic migrations.
- Integrate Redis session management with conversational state.
