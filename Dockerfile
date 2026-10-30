FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MALLOC_ARENA_MAX=2 \
    FRONTEND_DIST=/app/static \
    QUEUE_MODE=database \
    SECURE_COOKIES=1 \
    PORT=10000
RUN apt-get update && apt-get install -y --no-install-recommends redis-server \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home appuser
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium --only-shell \
    && chmod -R a+rX /opt/playwright
COPY --chown=appuser:appuser backend/ ./
COPY --from=frontend --chown=appuser:appuser /frontend/dist/ ./static/
COPY --chown=appuser:appuser deploy/render_runtime.py ./render_runtime.py
USER appuser
EXPOSE 10000
CMD ["python", "render_runtime.py"]
