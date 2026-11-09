FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

COPY mcp_services/after_sales_server/requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock && pip check

COPY mcp_services/after_sales_server/src ./src
COPY src/customer_service_policy ./src/customer_service_policy

EXPOSE 8100

CMD ["python", "-m", "after_sales_mcp.app"]
