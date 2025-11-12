# Project Notes

## Phase 1 Assumptions
- Google Calendar, Slack, and email providers are mocked with stub implementations until credentials are provided.
- Database and Redis URLs default to local development instances via `.env` configuration.
- n8n workflow will be populated in later phases once external integrations are ready.

## Outstanding Tasks
- Implement real Google Calendar client authentication flow.
- Add Slack event signature verification and interactive message handling.
- Create Alembic migration scripts for database schema evolution.
- Expand automated test coverage for services and routers.

## Slack Bot Integration Notes
- External Slack bot code imported as a git submodule under `slack_bot/` pointing to `sam9s/Grest_RACEN_Slack_Bot`.
- Bot is a Node.js project (entrypoint `slack-openai-bot/app.js`) and should be kept in sync with upstream via `git submodule update --remote` when changes are published.
- Ensure local `.env` files include Slack credentials for both FastAPI backend and bot before running end-to-end tests.
