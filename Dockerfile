# Two stages: build the React app with Node, then run everything with Python.
# The final image contains no Node, no node_modules and no TypeScript sources:
# only Python, the backend code and the built static files.

# ---- Stage 1: build the frontend -------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /frontend
# Copy the package files first: Docker caches this layer, so `npm ci` only
# reruns when the dependencies change, not on every code change.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Type-checks (tsc) and bundles into /frontend/dist
RUN npm run build

# ---- Stage 2: the Python app that serves API + frontend -------------------
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/app/data/solar.db \
    STATIC_DIR=/app/static

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /frontend/dist ./static

# Run as an unprivileged user, not root: if the app were ever compromised,
# the attacker would not own the container.
RUN useradd --create-home appuser && mkdir -p /app/data && chown appuser /app/data
USER appuser

EXPOSE 8000
# 0.0.0.0 = listen on all interfaces, so `docker run -p 8000:8000` can reach it.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
