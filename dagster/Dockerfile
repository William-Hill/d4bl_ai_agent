FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dagster.yaml workspace.yaml ./
COPY d4bl_pipelines/ ./d4bl_pipelines/

ENV DAGSTER_HOME=/app

EXPOSE 3003

CMD ["dagster-webserver", "-h", "0.0.0.0", "-p", "3003"]
