---
layout: default
title: API Reference
permalink: /api-reference/
---

# API Reference

## Overview

The D4BL Research Tool provides a command-line interface and will soon support a REST API.

## Command Line Interface

```bash
python d4bl.py [query] [--output {full,summary}] [--summary {brief,detailed,comprehensive}]
```

## Future REST API

### Planned Endpoints

```
POST /api/v1/research
GET  /api/v1/research/{job_id}
GET  /api/v1/research/{job_id}/status
POST /api/v1/analysis
POST /api/v1/summary
GET  /api/v1/jobs/{job_id}/results
```

### Example Usage

```python
from d4bl_client import D4BLClient

client = D4BLClient(api_key="your_api_key")

# Start research
research_job = client.research.create(
    query="How does algorithmic bias affect criminal justice?",
    summary_type="detailed"
)

# Check status
status = client.research.get_status(research_job.id)

# Get results
if status.is_complete:
    results = client.research.get_results(research_job.id)
    summary = results.summary
    analysis = results.analysis
``` 