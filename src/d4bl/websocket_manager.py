"""
Utilities for managing WebSocket connections and job log state.
"""
from __future__ import annotations

import queue
from typing import Dict, List, Optional

from fastapi import WebSocket

active_connections: Dict[str, WebSocket] = {}
job_logs: Dict[str, List[str]] = {}
log_queues: Dict[str, queue.Queue] = {}


async def send_websocket_update(job_id: str, message: dict) -> None:
    """Send a JSON payload to the client listening for job updates."""
    websocket = active_connections.get(job_id)
    if not websocket:
        return

    try:
        await websocket.send_json(message)
    except Exception as exc:  # noqa: BLE001 - best effort logging
        print(f"Error sending WebSocket update: {exc}")
        remove_connection(job_id)


def register_connection(job_id: str, websocket: WebSocket) -> None:
    """Associate an active WebSocket with a job id."""
    active_connections[job_id] = websocket


def remove_connection(job_id: str) -> None:
    """Remove the WebSocket connection for a job, if present."""
    active_connections.pop(job_id, None)


def create_log_queue(job_id: str) -> queue.Queue:
    """Create and track a queue for streaming job logs."""
    log_queue = queue.Queue()
    log_queues[job_id] = log_queue
    return log_queue


def get_log_queue(job_id: str) -> Optional[queue.Queue]:
    """Return the queue for a job, if it exists."""
    return log_queues.get(job_id)


def remove_log_queue(job_id: str) -> None:
    """Stop tracking the queue for a job."""
    log_queues.pop(job_id, None)


def set_job_logs(job_id: str, logs: List[str]) -> None:
    """Persist captured logs for later retrieval."""
    job_logs[job_id] = logs


def get_job_logs(job_id: str) -> List[str]:
    """Look up logs for a job."""
    return job_logs.get(job_id, [])

