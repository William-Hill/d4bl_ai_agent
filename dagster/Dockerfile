FROM python:3.12-slim

WORKDIR /app

COPY dagster/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dagster/dagster.yaml dagster/workspace.yaml ./
COPY dagster/d4bl_pipelines/ ./d4bl_pipelines/

ENV DAGSTER_HOME=/app

RUN addgroup --system dagster && adduser --system --ingroup dagster dagster \
    && chown -R dagster:dagster /app

USER dagster

EXPOSE 3003

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:3003/server_info')"]

CMD ["dagster-webserver", "-h", "0.0.0.0", "-p", "3003"]
