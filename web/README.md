# Web Dashboard (Vite + Vue)

This frontend calls the FastAPI server in `../server/src/main.py` and renders:

- API health
- tournament leaderboard and recent matches
- log stats summary and top performers
- player class breakdown

## Run locally

1. Start FastAPI (from the `server/src` directory):

```bash
uvicorn main:app --reload --port 8000
```

2. Start the Vite app (from this `web` directory):

```bash
npm run dev
```

The app targets `/api` by default in development (proxied by Vite to `http://127.0.0.1:8000`).

## Optional API base URL override

Create a `.env` file in the `web` folder:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

If `VITE_API_BASE_URL` is not set, the app uses `/api`.
