# ---------------------------------------------------------------------------
# Stage 1: Build the frontend SPA
# ---------------------------------------------------------------------------
FROM node:20-alpine AS frontend-build

ARG VITE_UI_LANG=de
ENV VITE_UI_LANG=$VITE_UI_LANG

WORKDIR /frontend

# Install dependencies first (better layer caching)
COPY frontend/package*.json ./
RUN npm ci

# Build the SPA
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: Backend (Python)
# ---------------------------------------------------------------------------
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including Docker CLI
RUN apt-get update && apt-get install -y \
    gcc \
    git \
    postgresql-client \
    ffmpeg \
    curl \
    && curl -fsSL https://get.docker.com | sh \
    && rm -rf /var/lib/apt/lists/*

# Allow git operations on mounted project directory
RUN git config --global --add safe.directory /project

# Copy requirements first for better caching
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ .

# Embed the compiled frontend so the backend can serve it on FRONTEND_PORT
COPY --from=frontend-build /frontend/dist /app/frontend_dist

# Expose API port and frontend port
EXPOSE 8000 80

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
