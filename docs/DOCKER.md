# Docker workflow

This project ships two images (API + frontend) and a Compose setup that runs them together.

## Prerequisites
- Docker Desktop or Docker Engine + Compose v2.
- Optional: Compose Watch (Docker Desktop 4.24+ / Compose 2.22+) for live-reload dev.

## Quick start (local build)
```bash
docker compose up --build
```

Open:
- Dashboard: http://127.0.0.1:3000
- API: http://127.0.0.1:8000

## API token
You can provide `API_KEY` via environment or set it in the dashboard UI. The API stores the token at `/data/.env` inside the container volume.

Example `.env` in repo root:
```bash
API_KEY=your_todoist_token_here
```

## Volumes and data
The API container persists data under `/data` and maps it to the `todoist-data` volume by default. This keeps cache/logs/token across restarts.

## Compose overrides
- API backend URL for the frontend is set via `API_URL` (defaults to `http://api:8000` in `compose.yaml`).
- Data persistence uses `TODOIST_DATA_DIR` and `TODOIST_CACHE_DIR` mapped to `/data`.
- Override image registry/user with `TODOIST_IMAGE_PREFIX` (defaults to `ghcr.io/mtyrolski`).

## Development (optional live reload)
```bash
docker compose watch
```
Watch is configured for the API service (sync + restart). For frontend changes, rebuild the image or run the Next.js dev server locally.

## Pull prebuilt images (GHCR)
Once the workflow publishes images:
```bash
docker compose pull
docker compose up
```

Images:
- `ghcr.io/<owner>/todoist-assistant-api`
- `ghcr.io/<owner>/todoist-assistant-frontend`

## Troubleshooting
- The API healthcheck hits `/api/health`. If the frontend waits, check logs with `docker compose logs -f api`.
- If you need local config changes, mount `configs/` into the API container or rebuild the image.
