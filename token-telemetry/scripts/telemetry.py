#!/usr/bin/env python3
import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "1.0"


def runtime_dir():
    return Path(os.environ.get("TOKEN_TELEMETRY_DIR", "~/.agents/data/token-telemetry")).expanduser()


def telemetry_file():
    return runtime_dir() / "telemetry.jsonl"


def baselines_file():
    return runtime_dir() / "baselines.jsonl"


def now():
    return datetime.now(timezone.utc).isoformat()


def append_record(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    record.setdefault("timestamp", now())
    record.setdefault("schema_version", SCHEMA_VERSION)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path):
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def normalize_invocation(raw, task_id, provider="ollama", model=None, location="local",
                        parent_invocation_id=None, retry_count=0, status="success",
                        telemetry_source="native_api"):
    measured = []
    for source_key, target_key in (
        ("prompt_eval_count", "input_tokens"),
        ("eval_count", "output_tokens"),
    ):
        if source_key in raw and raw[source_key] is not None:
            measured.append(target_key)
    for duration_key in ("prompt_eval_duration", "eval_duration", "load_duration", "total_duration"):
        if duration_key in raw and raw[duration_key] is not None:
            measured.append(duration_key)
    input_tokens = raw.get("prompt_eval_count")
    output_tokens = raw.get("eval_count")
    total_generated = output_tokens
    total_tokens = (
        input_tokens + output_tokens
        if input_tokens is not None and output_tokens is not None
        else None
    )
    duration = raw.get("total_duration")
    completeness = "complete" if input_tokens is not None and output_tokens is not None and duration is not None else (
        "partial" if measured else "missing"
    )
    return {
        "record_type": "invocation",
        "task_id": str(task_id),
        "invocation_id": str(uuid.uuid4()),
        "parent_invocation_id": parent_invocation_id,
        "provider": provider,
        "model": model or raw.get("model"),
        "execution_location": location,
        "input_tokens": input_tokens,
        "cached_input_tokens": None,
        "processing_tokens": None,
        "output_tokens": output_tokens,
        "total_generated_tokens": total_generated,
        "total_tokens": total_tokens,
        "duration_ns": duration,
        "status": status,
        "telemetry_source": telemetry_source,
        "telemetry_completeness": completeness,
        "measured_fields": measured,
        "retry_count": retry_count,
    }


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--task-id", required=True)
    end = sub.add_parser("finalize")
    end.add_argument("--task-id", required=True)
    end.add_argument("--status", choices=["passed", "failed"], required=True)
    baseline = sub.add_parser("baseline")
    baseline.add_argument("--task-id", required=True)
    baseline.add_argument("--remote-tokens", type=int, required=True)
    baseline.add_argument("--task-type")
    baseline.add_argument("--model")
    baseline.add_argument("--prompt-version")
    args = parser.parse_args()

    if args.command == "init":
        append_record(telemetry_file(), {
            "record_type": "task_start", "task_id": args.task_id,
            "invocation_id": None, "parent_invocation_id": None,
            "provider": "agent", "model": None, "execution_location": "unknown",
            "input_tokens": None, "cached_input_tokens": None, "processing_tokens": None,
            "output_tokens": None, "total_generated_tokens": None, "total_tokens": None,
            "duration_ns": None, "status": "started", "telemetry_source": "lifecycle",
            "telemetry_completeness": "missing", "measured_fields": [], "retry_count": 0,
        })
    elif args.command == "finalize":
        append_record(telemetry_file(), {
            "record_type": "task_end", "task_id": args.task_id,
            "invocation_id": None, "parent_invocation_id": None,
            "provider": "agent", "model": None, "execution_location": "unknown",
            "input_tokens": None, "cached_input_tokens": None, "processing_tokens": None,
            "output_tokens": None, "total_generated_tokens": None, "total_tokens": None,
            "duration_ns": None, "status": args.status, "telemetry_source": "lifecycle",
            "telemetry_completeness": "missing", "measured_fields": [], "retry_count": 0,
        })
    else:
        append_record(baselines_file(), {
            "record_type": "baseline", "task_id": args.task_id,
            "invocation_id": None, "parent_invocation_id": None,
            "provider": "remote", "model": args.model,
            "execution_location": "remote", "input_tokens": None,
            "cached_input_tokens": None, "processing_tokens": None, "output_tokens": None,
            "total_generated_tokens": None, "total_tokens": args.remote_tokens,
            "duration_ns": None, "status": "success", "telemetry_source": "manual_measured",
            "telemetry_completeness": "complete", "measured_fields": ["total_tokens"],
            "retry_count": 0, "task_type": args.task_type, "prompt_version": args.prompt_version,
        })
    print(str(telemetry_file() if args.command != "baseline" else baselines_file()))


if __name__ == "__main__":
    main()
