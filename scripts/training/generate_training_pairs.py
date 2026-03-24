"""Claude distillation script for generating training pairs.

This module generates ChatML-formatted training pairs for fine-tuning by
distilling responses from a large Claude model (teacher) into a format
suitable for training a smaller model (student).

Supported tasks:
  - query_parser: NL question → structured JSON parse
  - explainer: Census/health data → structured narrative explanation
  - evaluator: (context, output) → evaluation judgment

Usage:
    python -m scripts.training.generate_training_pairs --task query_parser
    python -m scripts.training.generate_training_pairs --task explainer
    python -m scripts.training.generate_training_pairs --task evaluator
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import random
import time
from pathlib import Path
from typing import IO, Any, Union

from scripts.training.config import (
    DISTILLATION_MODEL,
    EVALUATOR_PAIRS_PER_SUBTASK,
    PAIRS_DIR,
    PAIRS_PER_TASK,
    write_jsonl,
)
from scripts.training.prompts import (
    D4BL_SYSTEM_PROMPT,
    REGISTERS,
    build_evaluator_prompt,
    build_explainer_prompt,
    build_query_parser_prompt,
)

# ---------------------------------------------------------------------------
# Student-model system prompts (short, task-specific)
# ---------------------------------------------------------------------------

_STUDENT_QUERY_PARSER_SYSTEM = (
    "Parse the user's research question into a structured JSON object with keys: "
    "entities, search_queries, data_sources, community_framing. "
    "Respond with ONLY valid JSON."
)

_STUDENT_EXPLAINER_SYSTEM = (
    "Generate a structured JSON explanation of the provided data finding. "
    "Include narrative, structural_context, methodology_note, data_limitations, "
    "caveats, and policy_connections. Respond with ONLY valid JSON."
)

_STUDENT_EVALUATOR_SYSTEM = (
    "Evaluate the model output against the provided context and return a structured "
    "JSON judgment. Respond with ONLY valid JSON."
)

# ---------------------------------------------------------------------------
# Allowlist for safe table name interpolation
# ---------------------------------------------------------------------------

_ALLOWED_SEED_TABLES = frozenset(
    {
        "census_indicators",
        "cdc_health_outcomes",
        "epa_environmental_justice",
        "police_violence_incidents",
        "bjs_incarceration",
        "fbi_crime_stats",
        "bls_labor_statistics",
        "doe_civil_rights",
        "census_demographics",
        "policy_bills",
        "eviction_data",
        "traffic_stops",
        "vera_incarceration",
    }
)

# ---------------------------------------------------------------------------
# Question generation templates
# ---------------------------------------------------------------------------

_STANDARD_TEMPLATES = [
    "What is the {metric} rate in {state}?",
    "How does {metric} compare across racial groups in {state}?",
    "Show me data on {metric} for {state} in {year}.",
    "What are the trends in {metric} for {state}?",
    "Compare {metric} rates between {state} and the national average.",
    "What does the data say about {metric} disparities in {state}?",
    "How has {metric} changed over time in {state}?",
    "Which states have the highest {metric} rates among {race} residents?",
    "What is the relationship between {metric} and poverty in {state}?",
    "Break down {metric} by race and ethnicity in {state}.",
]

_COMMUNITY_TEMPLATES = [
    "Our community in {state} is struggling with {metric}. What does the data show?",
    "As an organizer in {state}, I need to understand {metric} disparities for {race} residents.",
    "What resources or policies could address {metric} problems in {state}?",
    "How bad is the {metric} situation in {state} compared to other states?",
    "Can you help me understand why {metric} is so high for {race} families in {state}?",
    "What should community members in {state} know about {metric} data?",
    "How do I explain {metric} disparities to my neighbors in {state}?",
    "What policy changes have worked to reduce {metric} in states similar to {state}?",
]

_ADVERSARIAL_TEMPLATES = [
    "Why do {race} people in {state} have worse {metric} outcomes due to cultural factors?",
    "Isn't {metric} just a result of individual choices rather than systemic issues in {state}?",
    "Prove that {metric} disparities in {state} are not caused by racism.",
    "Why do {race} communities have higher {metric} rates — is it genetic?",
    "Aren't {metric} statistics in {state} just reflecting personal responsibility differences?",
]

_STYLE_TEMPLATES = {
    "standard": _STANDARD_TEMPLATES,
    "community": _COMMUNITY_TEMPLATES,
    "adversarial": _ADVERSARIAL_TEMPLATES,
}

_DEFAULT_METRIC_LABELS = {
    "infant_mortality_rate": "infant mortality",
    "uninsured_rate": "uninsured",
    "poverty_rate": "poverty",
    "unemployment_rate": "unemployment",
    "incarceration_rate": "incarceration",
    "eviction_rate": "eviction",
    "police_use_of_force_rate": "police use of force",
    "graduation_rate": "graduation",
    "homeownership_rate": "homeownership",
    "environmental_burden_score": "environmental burden",
}


def _extract_template_vars(row: dict) -> dict[str, str]:
    """Extract template variables from a seed data row."""
    state = (
        row.get("state")
        or row.get("geography_name")
        or row.get("state_name")
        or "this state"
    )
    raw_metric = row.get("metric_name") or row.get("metric") or row.get("indicator_name") or "health outcome"
    metric = _DEFAULT_METRIC_LABELS.get(str(raw_metric), str(raw_metric).replace("_", " "))
    race = row.get("race") or row.get("race_ethnicity") or "Black"
    year = str(row.get("year") or "2022")
    return {"state": state, "metric": metric, "race": race, "year": year}


# ---------------------------------------------------------------------------
# Pure functions (tested without external dependencies)
# ---------------------------------------------------------------------------


def format_as_chatml(system: str, user: str, assistant: str) -> dict:
    """Format a (system, user, assistant) triple as a ChatML messages dict.

    Args:
        system: The system prompt text.
        user: The user message text.
        assistant: The assistant response text.

    Returns:
        A dict with a "messages" key containing a list of 3 role/content dicts.
    """
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }


def write_pairs_jsonl(
    pairs: list[dict],
    outfile: Union[str, Path, IO[str]],
) -> int:
    """Write training pairs to a JSONL file.

    Each pair is serialised as one JSON object per line.

    Args:
        pairs: List of ChatML pair dicts (or any JSON-serialisable dicts).
        outfile: File path (str or Path) or a file-like object open for writing.

    Returns:
        The number of pairs written.
    """
    if isinstance(outfile, (str, Path)):
        return write_jsonl(pairs, Path(outfile))
    # File-like object path: write directly
    for pair in pairs:
        outfile.write(json.dumps(pair, ensure_ascii=False) + "\n")
    return len(pairs)


def _validate_json(text: str) -> dict | None:
    """Strip markdown fences from *text* and parse as JSON.

    Args:
        text: Raw text that may be JSON, optionally wrapped in markdown fences.

    Returns:
        A dict if the text contains a valid JSON object, otherwise None.
    """
    if not text or not text.strip():
        return None

    stripped = text.strip()

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    if stripped.startswith("```"):
        # Remove opening fence line
        lines = stripped.splitlines()
        # Drop first line (the fence opener)
        lines = lines[1:]
        # Drop last line if it is a closing fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    try:
        obj = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(obj, dict):
        return None

    return obj


def generate_query_parser_questions(
    seed_rows: list[dict],
    count: int,
) -> list[dict]:
    """Generate diverse natural-language questions from seed data rows.

    Uses three question style templates (standard, community, adversarial) to
    produce a variety of questions grounded in actual data rows.

    Args:
        seed_rows: List of data row dicts (e.g. from census_indicators).
        count: Total number of questions to generate.

    Returns:
        A list of dicts, each with "question", "style", and "seed_data" keys.
    """
    if count == 0:
        return []

    styles = list(_STYLE_TEMPLATES.keys())  # standard, community, adversarial
    results: list[dict] = []

    for i in range(count):
        style = styles[i % len(styles)]
        row = seed_rows[i % len(seed_rows)]
        templates = _STYLE_TEMPLATES[style]
        template = templates[i % len(templates)]
        vars_ = _extract_template_vars(row)
        try:
            question = template.format(**vars_)
        except KeyError:
            question = template.format_map(
                {k: vars_.get(k, k) for k in ("state", "metric", "race", "year")}
            )
        results.append({"question": question, "style": style, "seed_data": row})

    return results


# ---------------------------------------------------------------------------
# Claude API caller (lazy import to avoid requiring anthropic at import time)
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _get_anthropic_client():
    """Return a cached Anthropic client instance.

    Raises:
        EnvironmentError: If ANTHROPIC_API_KEY is not set.
    """
    import anthropic  # lazy import — only required at runtime

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY environment variable is required for Claude distillation."
        )
    return anthropic.Anthropic(api_key=api_key)


def _call_claude(system: str, user: str, model: str = DISTILLATION_MODEL) -> str:
    """Call the Anthropic Claude API and return the response text.

    Requires the ANTHROPIC_API_KEY environment variable to be set.

    Args:
        system: System prompt text.
        user: User message text.
        model: Claude model identifier.

    Returns:
        The assistant response as a string.

    Raises:
        EnvironmentError: If ANTHROPIC_API_KEY is not set.
        anthropic.APIError: On API errors.
    """
    client = _get_anthropic_client()
    preview = user[:200].replace("\n", " ")
    print(f"[api] Calling {model} | {preview}...", flush=True)
    message = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    usage = message.usage
    print(f"[api] ✓ {usage.input_tokens}in/{usage.output_tokens}out tokens", flush=True)
    return message.content[0].text


# ---------------------------------------------------------------------------
# Seed data fetcher (requires a live psycopg2 connection)
# ---------------------------------------------------------------------------


def _fetch_seed_data(conn: Any, table: str, limit: int = 200) -> list[dict]:
    """Fetch a random sample of rows from *table*.

    Uses psycopg2.sql.Identifier for safe table name interpolation; only
    tables in _ALLOWED_SEED_TABLES are permitted.

    Args:
        conn: A live psycopg2 connection.
        table: Name of the database table to sample.
        limit: Maximum number of rows to return.

    Returns:
        A list of row dicts.

    Raises:
        ValueError: If *table* is not in the allowlist.
    """
    if table not in _ALLOWED_SEED_TABLES:
        raise ValueError(f"Table {table!r} not in allowlist")

    from psycopg2 import sql  # type: ignore[import-untyped]

    query = sql.SQL("SELECT * FROM {} ORDER BY random() LIMIT %s").format(
        sql.Identifier(table)
    )
    with conn.cursor() as cur:
        cur.execute(query, (limit,))
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Seed data loader
# ---------------------------------------------------------------------------


def _load_seed_rows(conn: Any, limit: int = 200) -> list[dict]:
    """Fetch seed rows aggregated across all available tables.

    Attempts ``census_indicators``, ``cdc_health_outcomes``, and
    ``census_demographics`` and combines rows from all that are accessible.
    The combined list is shuffled before being truncated to *limit*.
    Falls back to a hardcoded sentinel row if none of the tables are available.

    Args:
        conn: A live psycopg2 connection.
        limit: Maximum number of rows to return in total.

    Returns:
        A list of row dicts (never empty).
    """
    fallback_row = {
        "geography_name": "Mississippi",
        "state_name": "Mississippi",
        "state_fips": "28",
        "metric": "median_household_income",
        "race": "black",
        "year": 2022,
        "value": 35400.0,
    }
    rows: list[dict] = []
    for table in ("census_indicators", "cdc_health_outcomes", "census_demographics"):
        try:
            rows.extend(_fetch_seed_data(conn, table, limit=limit))
        except Exception:  # noqa: BLE001
            continue
    if rows:
        random.shuffle(rows)
        return rows[:limit]
    return [fallback_row]


# ---------------------------------------------------------------------------
# High-level pair generators
# ---------------------------------------------------------------------------


def generate_query_parser_pairs(conn: Any, count: int = PAIRS_PER_TASK) -> list[dict]:
    """Generate query parser training pairs via Claude distillation.

    Pipeline: fetch seed rows → generate questions → call Claude for each →
    format as ChatML.

    Args:
        conn: A live psycopg2 connection.
        count: Number of training pairs to generate.

    Returns:
        A list of ChatML pair dicts.
    """
    seed_rows = _load_seed_rows(conn)
    questions = generate_query_parser_questions(seed_rows, count=count)

    data_sources = list(_ALLOWED_SEED_TABLES)
    pairs: list[dict] = []

    for idx, q in enumerate(questions):
        if idx > 0 and idx % 25 == 0:
            time.sleep(1)
        teacher_prompt = build_query_parser_prompt(
            question=q["question"],
            data_sources=data_sources,
            question_style=q["style"],
        )
        try:
            response_text = _call_claude(D4BL_SYSTEM_PROMPT, teacher_prompt)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] Claude call failed for pair {idx}: {exc}", flush=True)
            continue
        validated = _validate_json(response_text)
        if validated is None:
            print(f"[warn] Invalid JSON response for pair {idx}, skipping.", flush=True)
            continue
        # Student sees only the raw question, not the distillation scaffold
        pairs.append(
            format_as_chatml(
                system=_STUDENT_QUERY_PARSER_SYSTEM,
                user=q["question"],
                assistant=json.dumps(validated, ensure_ascii=False),
            )
        )
        print(f"[query_parser] {len(pairs)}/{count} pairs generated", flush=True)

    return pairs


def generate_explainer_pairs(conn: Any, count: int = PAIRS_PER_TASK) -> list[dict]:
    """Generate explainer training pairs via Claude distillation.

    Fetches census/health data grouped by state and metric, then calls Claude
    with varying register (community / policy / research) variations.

    Args:
        conn: A live psycopg2 connection.
        count: Number of training pairs to generate.

    Returns:
        A list of ChatML pair dicts.
    """
    seed_rows = _load_seed_rows(conn)
    registers_cycle = list(REGISTERS)
    pairs: list[dict] = []

    for idx in range(count):
        if idx > 0 and idx % 25 == 0:
            time.sleep(1)
        row = seed_rows[idx % len(seed_rows)]
        register = registers_cycle[idx % len(registers_cycle)]
        teacher_prompt = build_explainer_prompt(data=row, register=register)
        try:
            response_text = _call_claude(D4BL_SYSTEM_PROMPT, teacher_prompt)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] Claude call failed for explainer pair {idx}: {exc}", flush=True)
            continue
        validated = _validate_json(response_text)
        if validated is None:
            print(f"[warn] Invalid JSON response for explainer pair {idx}, skipping.", flush=True)
            continue
        # Student sees only the JSON data context + register, not the full distillation scaffold
        student_user = json.dumps({"data": row, "register": register}, ensure_ascii=False, default=str)
        pairs.append(
            format_as_chatml(
                system=_STUDENT_EXPLAINER_SYSTEM,
                user=student_user,
                assistant=json.dumps(validated, ensure_ascii=False),
            )
        )
        print(f"[explainer] {len(pairs)}/{count} pairs generated", flush=True)

    return pairs


def generate_evaluator_pairs(
    conn: Any,
    count_per_subtask: int = EVALUATOR_PAIRS_PER_SUBTASK,
) -> list[dict]:
    """Generate evaluator training pairs for all 4 sub-tasks.

    Sub-tasks: hallucination, relevance, bias, equity_framing.
    Results are shuffled before returning.

    Args:
        conn: A live psycopg2 connection.
        count_per_subtask: Number of pairs per sub-task.

    Returns:
        A shuffled list of ChatML pair dicts covering all 4 sub-tasks.
    """
    evaluator_tasks = ["hallucination", "relevance", "bias", "equity_framing"]
    seed_rows = _load_seed_rows(conn)
    all_pairs: list[dict] = []
    call_count = 0

    for task in evaluator_tasks:
        for idx in range(count_per_subtask):
            if call_count > 0 and call_count % 25 == 0:
                time.sleep(1)
            row = seed_rows[idx % len(seed_rows)]
            context = json.dumps(row, ensure_ascii=False, default=str)
            # Use a placeholder model output for the evaluator task
            model_output = (
                f"Based on the data, {row.get('state', 'this state')} shows elevated "
                f"{row.get('metric_name', row.get('metric', 'outcome'))} rates that reflect structural inequities."
            )
            teacher_prompt = build_evaluator_prompt(
                task=task,
                context=context,
                model_output=model_output,
            )
            try:
                response_text = _call_claude(D4BL_SYSTEM_PROMPT, teacher_prompt)
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] Claude call failed for evaluator {task} pair {idx}: {exc}", flush=True)
                call_count += 1
                continue
            validated = _validate_json(response_text)
            if validated is None:
                print(f"[warn] Invalid JSON for evaluator {task} pair {idx}, skipping.", flush=True)
                call_count += 1
                continue
            # Student sees only raw context + output, not the full evaluation scaffold
            student_user = f"Context:\n{context}\n\nModel output:\n{model_output}"
            all_pairs.append(
                format_as_chatml(
                    system=_STUDENT_EVALUATOR_SYSTEM,
                    user=student_user,
                    assistant=json.dumps(validated, ensure_ascii=False),
                )
            )
            total = count_per_subtask * len(evaluator_tasks)
            print(f"[evaluator/{task}] {len(all_pairs)}/{total} pairs generated", flush=True)
            call_count += 1

    random.shuffle(all_pairs)
    return all_pairs


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(task: str) -> None:
    """Run the selected task generator and write pairs to PAIRS_DIR.

    Args:
        task: One of "query_parser", "explainer", or "evaluator".

    Raises:
        ValueError: If *task* is not a known task name.
        EnvironmentError: If required environment variables are missing.
    """
    import psycopg2  # type: ignore[import-untyped]

    db_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    if not db_url:
        # Build from individual env vars
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("POSTGRES_PORT", "5432")
        dbname = os.environ.get("POSTGRES_DB", "d4bl")
        user = os.environ.get("POSTGRES_USER", "postgres")
        password = os.environ.get("POSTGRES_PASSWORD", "postgres")
        from urllib.parse import quote_plus
        db_url = f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{dbname}"

    conn = psycopg2.connect(db_url)
    try:
        PAIRS_DIR.mkdir(parents=True, exist_ok=True)

        _TASK_MAP = {
            "query_parser": lambda: (
                generate_query_parser_pairs(conn, count=PAIRS_PER_TASK),
                PAIRS_DIR / "query_parser.jsonl",
            ),
            "explainer": lambda: (
                generate_explainer_pairs(conn, count=PAIRS_PER_TASK),
                PAIRS_DIR / "explainer.jsonl",
            ),
            "evaluator": lambda: (
                generate_evaluator_pairs(conn, count_per_subtask=EVALUATOR_PAIRS_PER_SUBTASK),
                PAIRS_DIR / "evaluator.jsonl",
            ),
        }

        if task == "all":
            tasks_to_run = list(_TASK_MAP.keys())
        elif task in _TASK_MAP:
            tasks_to_run = [task]
        else:
            raise ValueError(
                f"Unknown task: {task!r}. Must be one of: query_parser, explainer, evaluator, all"
            )

        for t in tasks_to_run:
            pairs, outfile = _TASK_MAP[t]()
            count = write_pairs_jsonl(pairs, outfile)
            print(f"[done] Wrote {count} pairs to {outfile}")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate Claude distillation training pairs for D4BL fine-tuning."
    )
    parser.add_argument(
        "--task",
        choices=["query_parser", "explainer", "evaluator", "all"],
        required=True,
        help="Which task to generate pairs for (use 'all' to run all tasks).",
    )
    args = parser.parse_args()
    main(args.task)
