#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from telemetry import baselines_file, read_jsonl, telemetry_file


def unavailable(reason):
    return {"value": None, "status": "unavailable", "reason": reason}


def pct(numerator, denominator):
    if denominator is None or denominator == 0:
        return unavailable("division by zero or baseline unavailable")
    return {"value": numerator / denominator * 100, "status": "available", "reason": None}


def sum_tokens(records, location, field):
    values = [r.get(field) for r in records if r.get("execution_location") == location
              and r.get("record_type") == "invocation"]
    measured = [v for v in values if v is not None]
    return sum(measured) if measured else None


def calculate(records, baselines=None, task_id=None, task_statuses=None):
    if task_id:
        records = [r for r in records if r.get("task_id") == task_id]
    invocations = [r for r in records if r.get("record_type") == "invocation"]
    local = sum_tokens(records, "local", "total_tokens")
    remote = sum_tokens(records, "remote", "total_tokens")

    baseline = None
    if baselines:
        candidates = [b for b in baselines if not task_id or b.get("task_id") == task_id]
        if candidates:
            baseline = candidates[-1].get("total_tokens")

    if remote is None:
        rtr = unavailable("remote token measurement unavailable")
    elif baseline is None:
        rtr = unavailable("comparable measured baseline unavailable")
    else:
        rtr = pct(1 - remote / baseline, 1)

    if local is None and remote is None:
        tdr = unavailable("local and remote token measurements unavailable")
    elif remote is None:
        tdr = unavailable("remote token measurement unavailable")
    elif local is None:
        tdr = unavailable("local token measurement unavailable")
    elif local + remote == 0:
        tdr = unavailable("division by zero")
    else:
        tdr = {"value": local / (local + remote) * 100, "status": "available", "reason": None}

    if local is None or remote is None or baseline is None:
        taf = unavailable("local, remote, or baseline measurement unavailable")
    elif baseline == 0:
        taf = unavailable("division by zero")
    else:
        taf = {"value": (local + remote) / baseline, "status": "available", "reason": None}

    if baseline is None or remote is None:
        rts = unavailable("baseline or remote token measurement unavailable")
    else:
        rts = {"value": baseline - remote, "status": "available", "reason": None}

    statuses = task_statuses or [
        r.get("status") for r in records if r.get("record_type") == "task_end"
    ]
    evaluated = len(statuses)
    if evaluated == 0:
        tsr = unavailable("no evaluated task result")
    else:
        tsr = {"value": sum(s == "passed" for s in statuses) / evaluated * 100,
               "status": "available", "reason": None}

    observed = len(invocations)
    measured = sum(r.get("total_tokens") is not None for r in invocations)
    tcr = unavailable("no observed invocations") if observed == 0 else {
        "value": measured / observed * 100, "status": "available", "reason": None
    }

    breakdown = {}
    for field in ("input_tokens", "processing_tokens", "output_tokens"):
        local_field = sum_tokens(records, "local", field)
        remote_field = sum_tokens(records, "remote", field)
        breakdown[field] = {
            "local": local_field,
            "remote": remote_field,
            "status": "available" if local_field is not None or remote_field is not None else "partial",
        }

    return {
        "RTR": rtr, "TDR": tdr, "TAF": taf, "RTS": rts, "TSR": tsr, "TCR": tcr,
        "breakdown": breakdown,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = calculate(read_jsonl(telemetry_file()), read_jsonl(baselines_file()), args.task_id)
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        for name in ("RTR", "TDR", "TAF", "RTS", "TSR", "TCR"):
            item = result[name]
            print(f"{name}: {item['value'] if item['value'] is not None else 'N/A'}"
                  f" ({item['status']}: {item['reason'] or 'ok'})")


if __name__ == "__main__":
    main()
