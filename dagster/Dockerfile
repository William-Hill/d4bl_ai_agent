FROM python:3.12-slim

WORKDIR /app

COPY dagster/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt uvicorn

COPY dagster/dagster.yaml dagster/workspace.yaml ./
COPY dagster/d4bl_pipelines/ ./d4bl_pipelines/
COPY dagster/auth_proxy.py dagster/entrypoint.sh ./

ENV DAGSTER_HOME=/app

RUN addgroup --system dagster && adduser --system --ingroup dagster dagster \
    && chown -R dagster:dagster /app \
    && chmod +x /app/entrypoint.sh

USER dagster

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/')"]

CMD ["/app/entrypoint.sh"]
