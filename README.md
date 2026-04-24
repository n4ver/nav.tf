# TF2 Analytics API

A full-stack web application designed for ingesting, analyzing, and visualizing Team Fortress 2 match logs.

This project provides tools to collect TF2 competitive log data (from sources like logs.tf), perform statistical analysis and rating aggregation, and present the data through a clean, interactive dashboard.

## Project Structure

The repository is organized into three main components:

- **`server/` (Backend)**: A FastAPI application managing the core data ingestion, processing, database interactions (via SQLModel and PostgreSQL), and API endpoints for retrieving player and match statistics.
- **`web/` (Frontend)**: A modern Vue.js application powered by Vite that serves as the dashboard. It visualizes data from the backend, including tournament leaderboards, match stats summaries, and player class breakdowns.
- **`classifier/` (Data Analysis)**: A Jupyter notebook environment intended for advanced data classification, predictive models, or deep-dive log analysis algorithms.

## Prerequisites

- **Docker & Docker Compose**: For running the PostgreSQL database and backend API easily.
- **Node.js & npm**: For running the Vue.js frontend locally.
- **Python 3.12+**: For running the backend or classifier locally without Docker.

## Setup & Running Locally

### Backend API & Database

The easiest way to run the backend and the database is using Docker Compose.

1. Navigate to the `server/` directory:
   ```bash
   cd server
   ```
2. Start the services with Docker Compose:
   ```bash
   docker-compose up -d --build
   ```
   This will start a PostgreSQL database and the FastAPI application exposed on `http://localhost:8000`.

Alternatively, to run the server locally without Docker (requires a running PostgreSQL database):
1. Create a virtual environment and install dependencies:
   ```bash
   cd server
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. Set your `DATABASE_URL` environment variable to point to your Postgres instance.
3. Start the FastAPI development server:
   ```bash
   cd src
   uvicorn main:app --reload --port 8000
   ```

### Web Dashboard

1. Navigate to the `web/` directory:
   ```bash
   cd web
   ```
2. Install the necessary NPM packages:
   ```bash
   npm install
   ```
3. Start the Vite development server:
   ```bash
   npm run dev
   ```
   The dashboard will be accessible via your browser (typically `http://localhost:5173`). By default, it proxies API requests to `http://127.0.0.1:8000`. You can override the API URL by creating a `.env` file in the `web/` folder with `VITE_API_BASE_URL=http://your-api-url`.

### Data Classifier

1. Navigate to the `classifier/` directory:
   ```bash
   cd classifier
   ```
2. Install the Jupyter environment requirements (preferably in a virtual environment):
   ```bash
   pip install -r src/requirements-classifier.txt
   ```
3. Open the notebook:
   ```bash
   jupyter notebook src/classifier.ipynb
   ```
