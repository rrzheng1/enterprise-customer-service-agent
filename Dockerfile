FROM node:24-alpine AS frontend-build
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock && pip check

COPY src ./src
COPY scripts ./scripts
COPY mcp_services ./mcp_services
COPY knowledge_base ./knowledge_base
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
COPY .env.example ./.env.example
COPY --from=frontend-build /ui/dist ./frontend/dist

EXPOSE 8000

CMD ["uvicorn", "customer_service_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
