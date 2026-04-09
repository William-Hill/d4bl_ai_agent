"""Claude distillation script for generating training pairs.

This module generates ChatML-formatted training pairs for fine-tuning by
distilling responses from a large Claude model (teacher) into a format
suitable for training a smaller model (student).

Supported tasks:
  - query_parser: NL question → structured JSON parse
  - explainer: Census/health data → structured narrative explanation
  - evaluator: (context, output) → evaluation judgment
  - evaluator_v2: Perturbation-based hallucination + tiered quality
  - query_parser_v2: Entity-type-diverse question parsing
  - evaluator_v3: Document-chunk hallucination detection
  - query_parser_v3: Community framing question parsing

Usage:
    python -m scripts.training.generate_training_pairs --task query_parser
    python -m scripts.training.generate_training_pairs --task all
    python -m scripts.training.generate_training_pairs --task evaluator_v2 --resume
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
    COMMUNITY_FRAMING_PAIRS,
    DISTILLATION_MODEL,
    DOC_EVALUATOR_PAIRS_PER_SUBTASK,
    EVALUATOR_PAIRS_PER_SUBTASK,
    EVALUATOR_V2_PAIRS_PER_SUBTASK,
    PAIRS_DIR,
    PAIRS_PER_TASK,
    PARSER_V2_ENTITY_PAIRS,
    write_jsonl,
)
from scripts.training.prompts import (
    COMMUNITY_FRAMING_QUESTION_TEMPLATES,
    D4BL_SYSTEM_PROMPT,
    ENTITY_TYPE_TEMPLATES,
    ORG_NAMES,
    PERTURBATION_TYPES,
    POLICY_NAMES,
    QUALITY_TIERS,
    REGISTERS,
    STRUCTURAL_FRAMES,
    STUDENT_EVALUATOR_SYSTEMS,
    build_evaluator_prompt,
    build_explainer_prompt,
    build_perturbation_prompt,
    build_query_parser_prompt,
    build_tiered_model_output_prompt,
)

# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------

# Claude Sonnet 4 pricing (per million tokens)
_COST_PER_M_INPUT = 3.00
_COST_PER_M_OUTPUT = 15.00

_total_input_tokens = 0
_total_output_tokens = 0
_total_calls = 0


def _track_cost(input_tokens: int, output_tokens: int) -> None:
    """Accumulate token usage and print running cost summary."""
    global _total_input_tokens, _total_output_tokens, _total_calls
    _total_input_tokens += input_tokens
    _total_output_tokens += output_tokens
    _total_calls += 1


def _cost_so_far() -> float:
    """Return estimated cost in USD based on accumulated token usage."""
    return (
        _total_input_tokens / 1_000_000 * _COST_PER_M_INPUT
        + _total_output_tokens / 1_000_000 * _COST_PER_M_OUTPUT
    )


def _print_cost_summary() -> None:
    """Print a human-readable cost summary to stdout."""
    cost = _cost_so_far()
    print(
        f"[cost] {_total_calls} API calls | "
        f"{_total_input_tokens:,} in + {_total_output_tokens:,} out tokens | "
        f"${cost:.2f} spent so far",
        flush=True,
    )


# ---------------------------------------------------------------------------
# Resume and incremental write helpers
# ---------------------------------------------------------------------------

_CHECKPOINT_FILE = ".checkpoint.json"
_DEFAULT_ENTRY: dict = {"last_attempted_idx": -1, "pairs_written": 0, "status": "pending"}


def _load_checkpoint(task: str, subtask: str = "_default", *, checkpoint_dir: Path | None = None) -> dict:
    """Load the checkpoint entry for a specific task/subtask.

    Args:
        task: Task name (e.g. "query_parser").
        subtask: Subtask name (e.g. "standard").
        checkpoint_dir: Directory containing the checkpoint file.  Defaults to PAIRS_DIR.

    Returns:
        Dict with keys ``last_attempted_idx``, ``pairs_written``, ``status``.
        Returns the default entry if the file or key is missing.
    """
    cp_dir = checkpoint_dir if checkpoint_dir is not None else PAIRS_DIR
    cp_file = cp_dir / _CHECKPOINT_FILE
    if not cp_file.exists():
        return dict(_DEFAULT_ENTRY)
    try:
        data = json.loads(cp_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(_DEFAULT_ENTRY)
    return dict(data.get(task, {}).get(subtask, _DEFAULT_ENTRY))


def _update_checkpoint(
    task: str,
    subtask: str = "_default",
    *,
    last_attempted_idx: int | None = None,
    pairs_written: int | None = None,
    status: str | None = None,
    checkpoint_dir: Path | None = None,
) -> None:
    """Merge provided fields into the checkpoint entry and write atomically.

    Only the supplied keyword arguments are updated; omitted fields retain their
    current values (or the default if the entry is new).

    Args:
        task: Task name.
        subtask: Subtask name.
        last_attempted_idx: Seed index of the last attempted pair.
        pairs_written: Number of pairs successfully written so far.
        status: Status string (e.g. "in_progress", "completed", "pending").
        checkpoint_dir: Directory containing the checkpoint file.  Defaults to PAIRS_DIR.
    """
    cp_dir = checkpoint_dir if checkpoint_dir is not None else PAIRS_DIR
    cp_dir.mkdir(parents=True, exist_ok=True)
    cp_file = cp_dir / _CHECKPOINT_FILE

    # Load existing data
    if cp_file.exists():
        try:
            data: dict = json.loads(cp_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    else:
        data = {}

    # Merge fields into the entry
    task_data = data.setdefault(task, {})
    entry = dict(task_data.get(subtask, _DEFAULT_ENTRY))
    if last_attempted_idx is not None:
        entry["last_attempted_idx"] = last_attempted_idx
    if pairs_written is not None:
        entry["pairs_written"] = pairs_written
    if status is not None:
        entry["status"] = status
    task_data[subtask] = entry

    # Atomic write via tmp file + os.replace
    tmp = cp_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, cp_file)


def _clear_checkpoint(task: str, *, checkpoint_dir: Path | None = None) -> None:
    """Remove all subtask entries for *task* from the checkpoint file.

    Args:
        task: Task name to remove.
        checkpoint_dir: Directory containing the checkpoint file.  Defaults to PAIRS_DIR.
    """
    cp_dir = checkpoint_dir if checkpoint_dir is not None else PAIRS_DIR
    cp_file = cp_dir / _CHECKPOINT_FILE
    if not cp_file.exists():
        return

    try:
        data: dict = json.loads(cp_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    data.pop(task, None)

    tmp = cp_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, cp_file)



def _open_incremental_writer(outfile: Path | None, resume: bool = False):
    """Open an incremental JSONL writer.

    Args:
        outfile: Path to write to, or None to skip file output.
        resume: If True, open in append mode to continue a previous run.

    Returns:
        A file handle (or None) suitable for incremental pair writing.
    """
    if outfile is None:
        return None
    outfile.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if resume else "w"
    return outfile.open(mode, encoding="utf-8")


def _write_pair(fh, pair: dict) -> None:
    """Write a single pair to an incremental JSONL file handle."""
    if fh is not None:
        fh.write(json.dumps(pair, ensure_ascii=False) + "\n")
        fh.flush()


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


def format_eval_user_message(context: str, model_output: str) -> str:
    """Format a (context, model_output) pair into the evaluator user message format.

    This format is load-bearing: ``apply_swap_augmentation`` in prepare_dataset.py
    parses it by splitting on the same separators.
    """
    return f"Context:\n{context}\n\nModel output:\n{model_output}"


def build_hallucination_pair(
    seed_row: dict,
    factual_response: str,
    hallucinated_response: str,
) -> tuple[dict, dict]:
    """Build a (FACTUAL, HALLUCINATED) pair for hallucination detection training.

    Returns:
        Tuple of (factual_pair, hallucinated_pair) in ChatML format.
    """
    system = STUDENT_EVALUATOR_SYSTEMS["hallucination"]
    context = json.dumps(seed_row, ensure_ascii=False, default=str)

    factual_pair = format_as_chatml(
        system=system,
        user=format_eval_user_message(context, factual_response),
        assistant=json.dumps({"label": "FACTUAL"}),
    )
    hallucinated_pair = format_as_chatml(
        system=system,
        user=format_eval_user_message(context, hallucinated_response),
        assistant=json.dumps({"label": "HALLUCINATED"}),
    )
    return factual_pair, hallucinated_pair


def build_evaluator_v2_pair(
    subtask: str,
    seed_row: dict,
    model_output: str,
    judgment: dict,
) -> dict:
    """Build a single evaluator training pair for relevance/bias/equity_framing.

    Args:
        subtask: One of "relevance", "bias", "equity_framing".
        seed_row: Source data row dict.
        model_output: The model response being evaluated.
        judgment: The expected evaluator judgment dict.

    Returns:
        ChatML-formatted training pair.
    """
    system = STUDENT_EVALUATOR_SYSTEMS[subtask]
    context = json.dumps(seed_row, ensure_ascii=False, default=str)
    return format_as_chatml(
        system=system,
        user=format_eval_user_message(context, model_output),
        assistant=json.dumps(judgment, ensure_ascii=False),
    )


def build_doc_hallucination_pair(
    chunk: dict,
    hallucinated_text: str,
) -> tuple[dict, dict]:
    """Build a (FACTUAL, HALLUCINATED) pair from a document chunk.

    The chunk content itself is the factual reference — no Claude call needed
    for the factual side. Only the hallucinated version requires generation.

    Args:
        chunk: Dict with keys: content, title, content_type.
        hallucinated_text: The perturbed/hallucinated version of the content.

    Returns:
        Tuple of (factual_pair, hallucinated_pair) in ChatML format.
    """
    system = STUDENT_EVALUATOR_SYSTEMS["hallucination"]
    context = json.dumps(
        {"title": chunk.get("title", ""), "content_type": chunk.get("content_type", ""),
         "source_text": chunk["content"]},
        ensure_ascii=False,
    )

    factual_pair = format_as_chatml(
        system=system,
        user=format_eval_user_message(context, chunk["content"]),
        assistant=json.dumps({"label": "FACTUAL"}),
    )
    hallucinated_pair = format_as_chatml(
        system=system,
        user=format_eval_user_message(context, hallucinated_text),
        assistant=json.dumps({"label": "HALLUCINATED"}),
    )
    return factual_pair, hallucinated_pair


def build_community_framing_pair(
    question: str,
    entities: list[str],
    data_sources: list[str],
    community_framing: dict,
) -> dict:
    """Build a parser training pair with a populated community_framing field.

    Args:
        question: The community-voiced research question.
        entities: Geographic/demographic entities in the question.
        data_sources: Relevant data source keys.
        community_framing: Dict with detected, issue_domain, structural_frame.

    Returns:
        ChatML-formatted training pair.
    """
    assistant_response = json.dumps({
        "entities": entities,
        "search_queries": [question],
        "data_sources": data_sources,
        "community_framing": community_framing,
    }, ensure_ascii=False)

    return format_as_chatml(
        system=_STUDENT_QUERY_PARSER_SYSTEM,
        user=question,
        assistant=assistant_response,
    )


_TEMPORAL_EVENTS = (
    "the 2008 recession", "COVID-19", "the Affordable Care Act",
    "the 2020 census", "Hurricane Katrina", "the Great Migration",
)


def generate_query_parser_questions_v2(
    seed_rows: list[dict],
    count: int,
    entity_type: str,
) -> list[dict]:
    """Generate questions for a specific entity type using v2 templates.

    Args:
        seed_rows: Seed data rows for template variable extraction.
        count: Number of questions to generate.
        entity_type: Key into ENTITY_TYPE_TEMPLATES.

    Returns:
        List of dicts with "question", "entity_type", and "seed_data" keys.
    """
    if count == 0:
        return []

    templates = ENTITY_TYPE_TEMPLATES[entity_type]
    results: list[dict] = []

    for i in range(count):
        row = seed_rows[i % len(seed_rows)]
        template = templates[i % len(templates)]
        vars_ = _extract_template_vars(row)
        # Add entity-type-specific variables
        vars_["org"] = ORG_NAMES[i % len(ORG_NAMES)]
        vars_["org2"] = ORG_NAMES[(i + 1) % len(ORG_NAMES)]
        vars_["policy"] = POLICY_NAMES[i % len(POLICY_NAMES)]
        vars_["county"] = row.get("county_name", row.get("geography_name", "Cook County"))
        vars_["county2"] = "Harris County"
        vars_["city"] = row.get("city", "Chicago")
        vars_["event"] = _TEMPORAL_EVENTS[i % len(_TEMPORAL_EVENTS)]
        try:
            vars_["year2"] = str(int(vars_["year"]) + 3)
        except (ValueError, TypeError):
            vars_["year2"] = "2025"
        vars_["metric2"] = "unemployment"
        vars_["metric3"] = "incarceration"
        vars_["state2"] = "California"
        vars_["demographic"] = "families"
        try:
            question = template.format(**vars_)
        except KeyError:
            question = template.format_map(vars_)
        results.append({
            "question": question,
            "entity_type": entity_type,
            "seed_data": row,
        })

    return results


def _generate_factual_response(seed_row: dict) -> str | None:
    """Call Claude to generate a grounded narrative from a seed row."""
    data_str = json.dumps(seed_row, ensure_ascii=False, default=str)
    prompt = (
        f"Write a 2-4 sentence factual summary of the following data. "
        f"Ground every claim in the provided data. Do not add information "
        f"not present in the data.\n\nData:\n{data_str}"
    )
    try:
        return _call_claude(D4BL_SYSTEM_PROMPT, prompt)
    except Exception as exc:
        print(f"[warn] Factual response generation failed: {exc}", flush=True)
        return None


def _perturb_to_hallucination(
    seed_row: dict,
    factual_response: str,
    perturbation_type: str,
) -> str | None:
    """Call Claude to create a hallucinated version of a factual response."""
    context = json.dumps(seed_row, ensure_ascii=False, default=str)
    prompt = build_perturbation_prompt(context, factual_response, perturbation_type)
    try:
        return _call_claude(D4BL_SYSTEM_PROMPT, prompt)
    except Exception as exc:
        print(f"[warn] Perturbation failed: {exc}", flush=True)
        return None


def _generate_tiered_model_output(seed_row: dict, quality_tier: str) -> str | None:
    """Call Claude to generate a model output at a specific quality tier."""
    prompt = build_tiered_model_output_prompt(seed_row, quality_tier)
    try:
        return _call_claude(D4BL_SYSTEM_PROMPT, prompt)
    except Exception as exc:
        print(f"[warn] Tiered output generation failed ({quality_tier}): {exc}", flush=True)
        return None


def generate_evaluator_pairs_v2(
    conn: Any,
    count_per_subtask: int = EVALUATOR_V2_PAIRS_PER_SUBTASK,
    outfile: Path | None = None,
    *,
    resume: bool = False,
    checkpoint_dir: Path | None = None,
) -> list[dict]:
    """Generate v2 evaluator training pairs using perturbation-based hallucinations.

    Hallucination subtask uses a three-step factual->perturb->format pipeline.
    Relevance, bias, equity_framing use tiered quality model outputs.

    Args:
        conn: A live psycopg2 connection.
        count_per_subtask: Number of pairs per subtask before dedup.
        outfile: Optional output path for incremental writes.
        resume: If True, skip already-completed subtasks via checkpoint state.
        checkpoint_dir: Optional directory for checkpoint files.

    Returns:
        A shuffled list of ChatML pair dicts.
    """
    seed_rows = _load_seed_rows(conn, limit=400)
    all_pairs: list[dict] = []
    call_count = 0

    task_name = "evaluator_v2"

    if not resume:
        _clear_checkpoint(task_name, checkpoint_dir=checkpoint_dir)

    fh = _open_incremental_writer(outfile, resume=resume)
    pair_count = 0
    if resume:
        for st in ["hallucination", "relevance", "bias", "equity_framing"]:
            st_cp = _load_checkpoint(task_name, st, checkpoint_dir=checkpoint_dir)
            pair_count += st_cp["pairs_written"]

    try:
        # --- Hallucination subtask: perturbation pipeline ---
        print("[evaluator_v2/hallucination] Starting perturbation pipeline...", flush=True)
        # Each seed generates 2 pairs (factual + hallucinated); use ceiling division
        # so odd count_per_subtask doesn't silently drop a pair
        hall_count = -(-count_per_subtask // 2)
        perturbation_types = list(PERTURBATION_TYPES)

        hall_cp = _load_checkpoint(task_name, "hallucination", checkpoint_dir=checkpoint_dir)
        if resume and hall_cp["status"] == "completed":
            print("[evaluator_v2/hallucination] Already completed — skipping", flush=True)
        else:
            subtask_start = pair_count
            for idx in range(hall_count):
                if resume and idx <= hall_cp["last_attempted_idx"]:
                    continue

                _update_checkpoint(
                    task_name, "hallucination",
                    last_attempted_idx=idx, status="in_progress",
                    checkpoint_dir=checkpoint_dir,
                )

                row = seed_rows[idx % len(seed_rows)]
                ptype = perturbation_types[idx % len(perturbation_types)]

                factual = _generate_factual_response(row)
                call_count += 1
                if call_count % 25 == 0:
                    time.sleep(1)
                if not factual:
                    continue

                hallucinated = _perturb_to_hallucination(row, factual, ptype)
                call_count += 1
                if call_count % 25 == 0:
                    time.sleep(1)
                if not hallucinated:
                    continue

                factual_pair, hall_pair = build_hallucination_pair(row, factual, hallucinated)
                all_pairs.extend([factual_pair, hall_pair])
                _write_pair(fh, factual_pair)
                _write_pair(fh, hall_pair)
                pair_count += 2
                print(
                    f"[evaluator_v2/hallucination] {pair_count} pairs "
                    f"({idx + 1}/{hall_count} seeds)", flush=True,
                )

            _update_checkpoint(
                task_name, "hallucination",
                pairs_written=pair_count - subtask_start, status="completed",
                checkpoint_dir=checkpoint_dir,
            )

        # --- Relevance, bias, equity_framing: tiered quality outputs ---
        non_hall_subtasks = ["relevance", "bias", "equity_framing"]

        for subtask in non_hall_subtasks:
            sub_cp = _load_checkpoint(task_name, subtask, checkpoint_dir=checkpoint_dir)
            if resume and sub_cp["status"] == "completed":
                print(f"[evaluator_v2/{subtask}] Already completed — skipping", flush=True)
                continue

            print(f"[evaluator_v2/{subtask}] Starting tiered generation...", flush=True)
            subtask_start = pair_count
            for idx in range(count_per_subtask):
                if resume and idx <= sub_cp["last_attempted_idx"]:
                    continue

                _update_checkpoint(
                    task_name, subtask,
                    last_attempted_idx=idx, status="in_progress",
                    checkpoint_dir=checkpoint_dir,
                )

                row = seed_rows[idx % len(seed_rows)]
                tier = QUALITY_TIERS[idx % len(QUALITY_TIERS)]

                model_output = _generate_tiered_model_output(row, tier)
                call_count += 1
                if call_count % 25 == 0:
                    time.sleep(1)
                if not model_output:
                    continue

                teacher_prompt = build_evaluator_prompt(
                    task=subtask,
                    context=json.dumps(row, ensure_ascii=False, default=str),
                    model_output=model_output,
                )
                try:
                    response_text = _call_claude(D4BL_SYSTEM_PROMPT, teacher_prompt)
                except Exception as exc:
                    print(f"[warn] Evaluator judgment failed for {subtask}: {exc}", flush=True)
                    call_count += 1
                    if call_count % 25 == 0:
                        time.sleep(1)
                    continue
                call_count += 1
                if call_count % 25 == 0:
                    time.sleep(1)

                validated = _validate_json(response_text)
                if validated is None:
                    print(f"[warn] Invalid JSON for {subtask} pair {idx}, skipping.", flush=True)
                    continue

                pair = build_evaluator_v2_pair(subtask, row, model_output, validated)
                all_pairs.append(pair)
                _write_pair(fh, pair)
                pair_count += 1
                print(
                    f"[evaluator_v2/{subtask}] {pair_count} total pairs", flush=True,
                )

            _update_checkpoint(
                task_name, subtask,
                pairs_written=pair_count - subtask_start, status="completed",
                checkpoint_dir=checkpoint_dir,
            )
    finally:
        if fh is not None:
            fh.close()
            print(f"[evaluator_v2] Saved {pair_count} pairs to {outfile}", flush=True)

    _print_cost_summary()
    return all_pairs


def generate_query_parser_pairs_v2(
    conn: Any,
    count: int = PARSER_V2_ENTITY_PAIRS,
    outfile: Path | None = None,
    *,
    resume: bool = False,
    checkpoint_dir: Path | None = None,
) -> list[dict]:
    """Generate v2 query parser pairs targeting diverse entity types.

    Generates questions across 6 entity type categories using expanded seed
    tables and new templates.

    Args:
        conn: A live psycopg2 connection.
        count: Total number of pairs to generate across all entity types.
        outfile: Optional output path for incremental writes.
        resume: If True, resume from the last checkpoint per entity type.
        checkpoint_dir: Directory for checkpoint file. Defaults to PAIRS_DIR.

    Returns:
        A list of ChatML pair dicts.
    """
    # Load expanded seed data including new tables
    seed_rows: list[dict] = []
    for table in list(_ALLOWED_SEED_TABLES):
        try:
            seed_rows.extend(_fetch_seed_data(conn, table, limit=100))
        except Exception:
            continue
    if not seed_rows:
        seed_rows = _load_seed_rows(conn)
    random.shuffle(seed_rows)

    # Distribute count across entity types per spec targets
    type_counts = {
        "organization": 50,
        "policy": 50,
        "sub_state_geography": 80,
        "intersectional": 40,
        "temporal": 30,
        "adversarial_json": 50,
    }
    # Validate type_counts keys match ENTITY_TYPE_TEMPLATES
    assert set(type_counts) == set(ENTITY_TYPE_TEMPLATES), (
        f"type_counts keys {set(type_counts)} != ENTITY_TYPE_TEMPLATES keys {set(ENTITY_TYPE_TEMPLATES)}"
    )
    # Scale if total count differs from 300
    total_specified = sum(type_counts.values())
    if count <= 0:
        return []
    if count != total_specified:
        scale = count / total_specified
        type_counts = {k: max(1, round(v * scale)) for k, v in type_counts.items()}

    data_sources = list(_ALLOWED_SEED_TABLES)
    pairs: list[dict] = []

    task_name = "query_parser_v2"

    if not resume:
        _clear_checkpoint(task_name, checkpoint_dir=checkpoint_dir)

    fh = _open_incremental_writer(outfile, resume=resume)
    pair_count = 0
    if resume:
        for et in type_counts:
            et_cp = _load_checkpoint(task_name, et, checkpoint_dir=checkpoint_dir)
            pair_count += et_cp["pairs_written"]

    try:
        for entity_type, type_count in type_counts.items():
            cp = _load_checkpoint(task_name, entity_type, checkpoint_dir=checkpoint_dir)
            if resume and cp["status"] == "completed":
                print(f"[{task_name}/{entity_type}] Already completed — skipping", flush=True)
                continue

            subtask_start = pair_count
            questions = generate_query_parser_questions_v2(
                seed_rows, count=type_count, entity_type=entity_type,
            )
            for idx, q in enumerate(questions):
                if resume and idx <= cp["last_attempted_idx"]:
                    continue

                _update_checkpoint(task_name, entity_type, last_attempted_idx=idx, status="in_progress",
                                   checkpoint_dir=checkpoint_dir)

                if idx > 0 and idx % 25 == 0:
                    time.sleep(1)

                teacher_prompt = build_query_parser_prompt(
                    question=q["question"],
                    data_sources=data_sources,
                    question_style="adversarial" if entity_type == "adversarial_json" else "standard",
                )
                try:
                    response_text = _call_claude(D4BL_SYSTEM_PROMPT, teacher_prompt)
                except Exception as exc:
                    print(f"[warn] Claude call failed for {entity_type} pair {idx}: {exc}", flush=True)
                    continue

                validated = _validate_json(response_text)
                if validated is None:
                    print(f"[warn] Invalid JSON for {entity_type} pair {idx}, skipping.", flush=True)
                    continue

                pair = format_as_chatml(
                    system=_STUDENT_QUERY_PARSER_SYSTEM,
                    user=q["question"],
                    assistant=json.dumps(validated, ensure_ascii=False),
                )
                pairs.append(pair)
                _write_pair(fh, pair)
                pair_count += 1
                print(f"[query_parser_v2/{entity_type}] {pair_count} total pairs", flush=True)

            _update_checkpoint(task_name, entity_type, pairs_written=pair_count - subtask_start,
                               status="completed", checkpoint_dir=checkpoint_dir)
    finally:
        if fh is not None:
            fh.close()
            print(f"[query_parser_v2] Saved {pair_count} pairs to {outfile}", flush=True)

    _print_cost_summary()
    return pairs


# ---------------------------------------------------------------------------
# V3 generators: document-sourced evaluator + community framing parser
# ---------------------------------------------------------------------------


def generate_doc_hallucination_pairs(
    conn: Any,
    count_per_subtask: int = DOC_EVALUATOR_PAIRS_PER_SUBTASK,
    outfile: Path | None = None,
    *,
    resume: bool = False,
    checkpoint_dir: Path | None = None,
) -> list[dict]:
    """Generate v3 evaluator pairs from document chunks.

    Fetches random document chunks, perturbs each into a hallucinated version
    via Claude, then uses build_doc_hallucination_pair to create paired
    FACTUAL/HALLUCINATED training examples.

    Args:
        conn: A live psycopg2 connection.
        count_per_subtask: Number of chunks to process (yields 2x pairs).
        outfile: Optional output path for incremental writes.
        resume: If True, skip already-completed work via checkpoint state.
        checkpoint_dir: Optional directory for checkpoint files.

    Returns:
        A list of ChatML pair dicts.
    """
    import psycopg2.extras

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT dc.content, d.title, d.content_type "
            "FROM document_chunks dc "
            "JOIN documents d ON dc.document_id = d.id "
            "WHERE length(dc.content) > 80 "
            "ORDER BY random() LIMIT %s",
            (count_per_subtask,),
        )
        chunks = [dict(row) for row in cur.fetchall()]

    if not chunks:
        print("[evaluator_v3] No document chunks found — skipping", flush=True)
        return []

    task_name = "evaluator_v3"
    subtask = "_default"

    if not resume:
        _clear_checkpoint(task_name, checkpoint_dir=checkpoint_dir)

    cp = _load_checkpoint(task_name, subtask, checkpoint_dir=checkpoint_dir)
    if resume and cp["status"] == "completed":
        print(f"[{task_name}] Already completed — skipping", flush=True)
        return []

    fh = _open_incremental_writer(outfile, resume=resume)
    pairs: list[dict] = []
    pair_count = cp["pairs_written"] if resume else 0
    perturbation_types = list(PERTURBATION_TYPES)

    try:
        for idx, chunk in enumerate(chunks):
            if resume and idx <= cp["last_attempted_idx"]:
                continue

            _update_checkpoint(
                task_name, subtask,
                last_attempted_idx=idx, status="in_progress",
                checkpoint_dir=checkpoint_dir,
            )

            ptype = perturbation_types[idx % len(perturbation_types)]
            context = json.dumps(
                {"title": chunk["title"], "content_type": chunk["content_type"]},
                ensure_ascii=False,
            )
            prompt = build_perturbation_prompt(context, chunk["content"], ptype)

            try:
                hallucinated = _call_claude(D4BL_SYSTEM_PROMPT, prompt)
            except Exception as exc:
                print(f"[warn] Doc perturbation failed: {exc}", flush=True)
                continue

            if not hallucinated:
                continue

            factual_pair, hall_pair = build_doc_hallucination_pair(chunk, hallucinated)
            pairs.extend([factual_pair, hall_pair])
            _write_pair(fh, factual_pair)
            _write_pair(fh, hall_pair)
            pair_count += 2
            print(
                f"[evaluator_v3] {pair_count} pairs ({idx + 1}/{len(chunks)} chunks)",
                flush=True,
            )

            if (idx + 1) % 25 == 0:
                time.sleep(1)

        _update_checkpoint(
            task_name, subtask,
            pairs_written=pair_count, status="completed",
            checkpoint_dir=checkpoint_dir,
        )
    finally:
        if fh is not None:
            fh.close()
            print(f"[evaluator_v3] Saved {pair_count} pairs to {outfile}", flush=True)

    _print_cost_summary()
    return pairs


_FRAMING_RACES = [
    "Black", "Latino", "Indigenous", "Asian American", "Pacific Islander",
]

_FRAMING_STATES = [
    "Alabama", "Georgia", "Mississippi", "Louisiana", "Texas",
    "California", "New York", "Illinois", "Ohio", "Michigan",
    "North Carolina", "Florida", "Pennsylvania", "Virginia", "Tennessee",
]

_FRAMING_ISSUE_LABELS: dict[str, str] = {
    "housing": "housing discrimination",
    "criminal_justice": "criminal justice inequality",
    "voting_rights": "voter suppression",
    "education": "education funding disparities",
    "health": "health access disparities",
    "economic_justice": "economic inequality",
    "environmental_justice": "environmental injustice",
}

_BILL_NUMBERS = [
    "HB 1234", "SB 567", "HB 890", "SB 101", "HB 2345",
]


def _build_framing_example(idx: int) -> tuple[str, list[str], dict]:
    """Build a single community-framing training example deterministically.

    Cycles through domains, frames, races, states, and templates using idx
    to ensure balanced, reproducible coverage across all combinations.
    """
    domains = list(STRUCTURAL_FRAMES.keys())
    templates = COMMUNITY_FRAMING_QUESTION_TEMPLATES

    domain = domains[idx % len(domains)]
    frames = STRUCTURAL_FRAMES[domain]
    frame = frames[idx % len(frames)]
    race = _FRAMING_RACES[idx % len(_FRAMING_RACES)]
    state = _FRAMING_STATES[idx % len(_FRAMING_STATES)]
    issue = _FRAMING_ISSUE_LABELS[domain]

    # Pick a related issue from a different domain for cross-domain templates
    other_domain = domains[(idx + 1) % len(domains)]
    related_issue = _FRAMING_ISSUE_LABELS[other_domain]

    template = templates[idx % len(templates)]
    question = template.format(
        state=state,
        race=race,
        issue=issue,
        related_issue=related_issue,
        bill_number=_BILL_NUMBERS[idx % len(_BILL_NUMBERS)],
    )

    entities = [state, race]
    community_framing = {
        "detected": True,
        "issue_domain": domain,
        "structural_frame": frame,
    }

    return question, entities, community_framing


def generate_community_framing_pairs(
    conn: Any,
    count: int = COMMUNITY_FRAMING_PAIRS,
    outfile: Path | None = None,
    *,
    resume: bool = False,
    checkpoint_dir: Path | None = None,
) -> list[dict]:
    """Generate v3 parser pairs with populated community_framing fields.

    Uses COMMUNITY_FRAMING_QUESTION_TEMPLATES to build questions that sound
    like community organizers asking about equity data. No Claude calls needed
    — the ground truth is deterministic from the template parameters.

    Args:
        conn: A live psycopg2 connection (unused but kept for signature parity).
        count: Number of pairs to generate.
        outfile: Optional output path for incremental writes.
        resume: If True, resume from the last checkpoint.
        checkpoint_dir: Directory for checkpoint file. Defaults to PAIRS_DIR.

    Returns:
        A list of ChatML pair dicts.
    """
    task_name = "query_parser_v3"
    subtask = "_default"

    if not resume:
        _clear_checkpoint(task_name, checkpoint_dir=checkpoint_dir)

    cp = _load_checkpoint(task_name, subtask, checkpoint_dir=checkpoint_dir)
    if resume and cp["status"] == "completed":
        print(f"[{task_name}] Already completed — skipping", flush=True)
        return []

    fh = _open_incremental_writer(outfile, resume=resume)
    pairs: list[dict] = []
    pair_count = cp["pairs_written"] if resume else 0
    data_sources = list(_ALLOWED_SEED_TABLES)

    try:
        for idx in range(count):
            if resume and idx <= cp["last_attempted_idx"]:
                continue

            _update_checkpoint(task_name, subtask, last_attempted_idx=idx, status="in_progress",
                               checkpoint_dir=checkpoint_dir)

            question, entities, community_framing = _build_framing_example(idx)

            pair = build_community_framing_pair(
                question, entities, data_sources, community_framing,
            )
            pairs.append(pair)
            _write_pair(fh, pair)
            pair_count += 1

            if pair_count % 50 == 0:
                print(f"[query_parser_v3] {pair_count}/{count} pairs", flush=True)

        _update_checkpoint(task_name, subtask, pairs_written=pair_count, status="completed",
                           checkpoint_dir=checkpoint_dir)
    finally:
        if fh is not None:
            fh.close()
            print(f"[query_parser_v3] Saved {pair_count} pairs to {outfile}", flush=True)

    return pairs


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
    _track_cost(usage.input_tokens, usage.output_tokens)
    print(f"[api] ✓ {usage.input_tokens}in/{usage.output_tokens}out tokens", flush=True)
    if _total_calls % 10 == 0:
        _print_cost_summary()
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
    seed_tables = (
        "census_indicators",
        "cdc_health_outcomes",
        "census_demographics",
        "policy_bills",
        "bjs_incarceration",
        "vera_incarceration",
        "police_violence_incidents",
        "epa_environmental_justice",
    )
    rows: list[dict] = []
    for table in seed_tables:
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


def generate_query_parser_pairs(
    conn: Any,
    count: int = PAIRS_PER_TASK,
    outfile: Path | None = None,
    *,
    resume: bool = False,
    checkpoint_dir: Path | None = None,
) -> list[dict]:
    """Generate query parser training pairs via Claude distillation.

    Pipeline: fetch seed rows → generate questions → call Claude for each →
    format as ChatML.

    Args:
        conn: A live psycopg2 connection.
        count: Number of training pairs to generate.
        outfile: If provided, pairs are appended incrementally so partial
            progress survives interruption.
        resume: If True, resume from the last checkpoint.
        checkpoint_dir: Directory for checkpoint file. Defaults to PAIRS_DIR.

    Returns:
        A list of ChatML pair dicts.
    """
    task_name = "query_parser"
    subtask = "_default"

    if not resume:
        _clear_checkpoint(task_name, checkpoint_dir=checkpoint_dir)

    cp = _load_checkpoint(task_name, subtask, checkpoint_dir=checkpoint_dir)
    if resume and cp["status"] == "completed":
        print(f"[{task_name}] Already completed — skipping", flush=True)
        return []

    seed_rows = _load_seed_rows(conn)
    questions = generate_query_parser_questions(seed_rows, count=count)

    data_sources = list(_ALLOWED_SEED_TABLES)
    pairs: list[dict] = []

    fh = _open_incremental_writer(outfile, resume=resume)
    pair_count = cp["pairs_written"] if resume else 0

    try:
        for idx, q in enumerate(questions):
            if resume and idx <= cp["last_attempted_idx"]:
                continue

            _update_checkpoint(task_name, subtask, last_attempted_idx=idx, status="in_progress",
                               checkpoint_dir=checkpoint_dir)

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
            pair = format_as_chatml(
                system=_STUDENT_QUERY_PARSER_SYSTEM,
                user=q["question"],
                assistant=json.dumps(validated, ensure_ascii=False),
            )
            pairs.append(pair)
            _write_pair(fh, pair)
            pair_count += 1
            print(f"[query_parser] {pair_count}/{count} pairs generated", flush=True)

        _update_checkpoint(task_name, subtask, pairs_written=pair_count, status="completed",
                           checkpoint_dir=checkpoint_dir)
    finally:
        if fh is not None:
            fh.close()
            print(f"[query_parser] Saved {pair_count} pairs to {outfile}", flush=True)

    return pairs


def generate_explainer_pairs(
    conn: Any,
    count: int = PAIRS_PER_TASK,
    outfile: Path | None = None,
    *,
    resume: bool = False,
    checkpoint_dir: Path | None = None,
) -> list[dict]:
    """Generate explainer training pairs via Claude distillation.

    Fetches census/health data grouped by state and metric, then calls Claude
    with varying register (community / policy / research) variations.

    Args:
        conn: A live psycopg2 connection.
        count: Number of training pairs to generate.
        outfile: If provided, pairs are appended incrementally so partial
            progress survives interruption.
        resume: If True, resume from the last checkpoint.
        checkpoint_dir: Directory for checkpoint file. Defaults to PAIRS_DIR.

    Returns:
        A list of ChatML pair dicts.
    """
    task_name = "explainer"
    subtask = "_default"

    if not resume:
        _clear_checkpoint(task_name, checkpoint_dir=checkpoint_dir)

    cp = _load_checkpoint(task_name, subtask, checkpoint_dir=checkpoint_dir)
    if resume and cp["status"] == "completed":
        print(f"[{task_name}] Already completed — skipping", flush=True)
        return []

    seed_rows = _load_seed_rows(conn)
    registers_cycle = list(REGISTERS)
    pairs: list[dict] = []

    fh = _open_incremental_writer(outfile, resume=resume)
    pair_count = cp["pairs_written"] if resume else 0

    try:
        for idx in range(count):
            if resume and idx <= cp["last_attempted_idx"]:
                continue

            _update_checkpoint(task_name, subtask, last_attempted_idx=idx, status="in_progress",
                               checkpoint_dir=checkpoint_dir)

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
            student_user = json.dumps({"data": row, "register": register}, ensure_ascii=False, default=str)
            pair = format_as_chatml(
                system=_STUDENT_EXPLAINER_SYSTEM,
                user=student_user,
                assistant=json.dumps(validated, ensure_ascii=False),
            )
            pairs.append(pair)
            _write_pair(fh, pair)
            pair_count += 1
            print(f"[explainer] {pair_count}/{count} pairs generated", flush=True)

        _update_checkpoint(task_name, subtask, pairs_written=pair_count, status="completed",
                           checkpoint_dir=checkpoint_dir)
    finally:
        if fh is not None:
            fh.close()
            print(f"[explainer] Saved {pair_count} pairs to {outfile}", flush=True)

    return pairs


def generate_evaluator_pairs(
    conn: Any,
    count_per_subtask: int = EVALUATOR_PAIRS_PER_SUBTASK,
    outfile: Path | None = None,
    *,
    resume: bool = False,
    checkpoint_dir: Path | None = None,
) -> list[dict]:
    """Generate evaluator training pairs for all 4 sub-tasks.

    Sub-tasks: hallucination, relevance, bias, equity_framing.
    Results are shuffled before returning.

    Args:
        conn: A live psycopg2 connection.
        count_per_subtask: Number of pairs per sub-task.
        outfile: If provided, pairs are buffered in memory and written
            (shuffled) on completion or interruption.
        resume: If True, resume from the last checkpoint per subtask.
        checkpoint_dir: Directory for checkpoint file. Defaults to PAIRS_DIR.

    Returns:
        A shuffled list of ChatML pair dicts covering all 4 sub-tasks.
    """
    evaluator_tasks = ["hallucination", "relevance", "bias", "equity_framing"]
    seed_rows = _load_seed_rows(conn)
    all_pairs: list[dict] = []
    call_count = 0
    total = count_per_subtask * len(evaluator_tasks)

    task_name = "evaluator"

    if not resume:
        _clear_checkpoint(task_name, checkpoint_dir=checkpoint_dir)

    fh = _open_incremental_writer(outfile, resume=resume)
    pair_count = 0
    if resume:
        for st in evaluator_tasks:
            st_cp = _load_checkpoint(task_name, st, checkpoint_dir=checkpoint_dir)
            pair_count += st_cp["pairs_written"]

    try:
        for task_idx, task in enumerate(evaluator_tasks):
            cp = _load_checkpoint(task_name, task, checkpoint_dir=checkpoint_dir)
            if resume and cp["status"] == "completed":
                print(f"[{task_name}/{task}] Already completed — skipping", flush=True)
                continue

            subtask_start = pair_count
            for idx in range(count_per_subtask):
                if resume and idx <= cp["last_attempted_idx"]:
                    continue

                _update_checkpoint(task_name, task, last_attempted_idx=idx, status="in_progress",
                                   checkpoint_dir=checkpoint_dir)

                if call_count > 0 and call_count % 25 == 0:
                    time.sleep(1)
                call_count += 1
                row = seed_rows[idx % len(seed_rows)]
                context = json.dumps(row, ensure_ascii=False, default=str)
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
                    continue
                validated = _validate_json(response_text)
                if validated is None:
                    print(f"[warn] Invalid JSON for evaluator {task} pair {idx}, skipping.", flush=True)
                    continue
                student_user = f"Context:\n{context}\n\nModel output:\n{model_output}"
                pair = format_as_chatml(
                    system=_STUDENT_EVALUATOR_SYSTEM,
                    user=student_user,
                    assistant=json.dumps(validated, ensure_ascii=False),
                )
                all_pairs.append(pair)
                _write_pair(fh, pair)
                pair_count += 1
                print(f"[evaluator/{task}] {pair_count}/{total} pairs generated", flush=True)

            _update_checkpoint(task_name, task, pairs_written=pair_count - subtask_start,
                               status="completed", checkpoint_dir=checkpoint_dir)
    finally:
        if fh is not None:
            fh.close()
            print(f"[evaluator] Saved {pair_count} pairs to {outfile}", flush=True)

    return all_pairs


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Generate Claude distillation training pairs for D4BL fine-tuning."
    )
    parser.add_argument(
        "--task",
        choices=[
            "query_parser", "explainer", "evaluator",
            "evaluator_v2", "query_parser_v2",
            "evaluator_v3", "query_parser_v3",
            "all",
        ],
        required=True,
        help="Which task to generate pairs for (use 'all' to run all tasks).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=False,
        help="Resume from checkpoint instead of starting fresh.",
    )
    return parser


def main(task: str, *, resume: bool = False) -> None:
    """Run the selected task generator and write pairs to PAIRS_DIR.

    Args:
        task: One of the task names in _TASK_MAP, or "all".
        resume: If True, skip tasks whose checkpoint status is "completed"
            instead of clearing checkpoints and starting fresh.

    Raises:
        ValueError: If *task* is not a known task name.
        EnvironmentError: If required environment variables are missing.
    """
    import psycopg2  # type: ignore[import-untyped]

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    db_url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("POSTGRES_URL")
        or os.environ.get("DAGSTER_POSTGRES_URL")
    )
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
            "query_parser": lambda: generate_query_parser_pairs(
                conn, count=PAIRS_PER_TASK, outfile=PAIRS_DIR / "query_parser.jsonl",
                resume=resume,
            ),
            "explainer": lambda: generate_explainer_pairs(
                conn, count=PAIRS_PER_TASK, outfile=PAIRS_DIR / "explainer.jsonl",
                resume=resume,
            ),
            "evaluator": lambda: generate_evaluator_pairs(
                conn, count_per_subtask=EVALUATOR_PAIRS_PER_SUBTASK,
                outfile=PAIRS_DIR / "evaluator.jsonl",
                resume=resume,
            ),
            "evaluator_v2": lambda: generate_evaluator_pairs_v2(
                conn, count_per_subtask=EVALUATOR_V2_PAIRS_PER_SUBTASK,
                outfile=PAIRS_DIR / "evaluator_v2.jsonl",
                resume=resume,
            ),
            "query_parser_v2": lambda: generate_query_parser_pairs_v2(
                conn, count=PARSER_V2_ENTITY_PAIRS,
                outfile=PAIRS_DIR / "query_parser_v2.jsonl",
                resume=resume,
            ),
            "evaluator_v3": lambda: generate_doc_hallucination_pairs(
                conn, count_per_subtask=DOC_EVALUATOR_PAIRS_PER_SUBTASK,
                outfile=PAIRS_DIR / "evaluator_v3.jsonl",
                resume=resume,
            ),
            "query_parser_v3": lambda: generate_community_framing_pairs(
                conn, count=COMMUNITY_FRAMING_PAIRS,
                outfile=PAIRS_DIR / "query_parser_v3.jsonl",
                resume=resume,
            ),
        }

        if task == "all":
            tasks_to_run = list(_TASK_MAP.keys())
        elif task in _TASK_MAP:
            tasks_to_run = [task]
        else:
            raise ValueError(
                f"Unknown task: {task!r}. Must be one of: {', '.join(_TASK_MAP.keys())}, all"
            )

        for t in tasks_to_run:
            # Each generator handles its own checkpoint clear/check internally.
            # The main() check here is a fast-path for --task all --resume
            # to skip entirely-completed single-subtask tasks.
            if resume:
                cp = _load_checkpoint(t)
                if cp["status"] == "completed":
                    print(f"[{t}] Already completed — skipping (use without --resume to regenerate)")
                    continue
            pairs = _TASK_MAP[t]()
            print(f"[done] {t}: {len(pairs)} pairs")
            _print_cost_summary()

        print("\n" + "=" * 60)
        print("FINAL COST SUMMARY")
        print("=" * 60)
        _print_cost_summary()
        print("=" * 60)
    finally:
        conn.close()


if __name__ == "__main__":
    _parser = _build_arg_parser()
    _args = _parser.parse_args()
    main(_args.task, resume=_args.resume)
