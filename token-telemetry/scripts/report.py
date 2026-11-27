#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kpi import calculate, sum_tokens
from telemetry import baselines_file, read_jsonl, telemetry_file


def fmt(value, suffix="", digits=2):
    if value is None:
        return "N/A"
    if digits == 0 and isinstance(value, int):
        return f"{value}{suffix}"
    return f"{value:.{digits}f}{suffix}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    records = read_jsonl(telemetry_file())
    baselines = read_jsonl(baselines_file())
    kpis = calculate(records, baselines, args.task_id)
    selected = [r for r in records if not args.task_id or r.get("task_id") == args.task_id]
    invocations = [r for r in selected if r.get("record_type") == "invocation"]

    ends = [r for r in selected if r.get("record_type") == "task_end"]
    status = ends[-1]["status"] if ends else "unknown"
    local = sum_tokens(invocations, "local", "total_tokens")
    remote = sum_tokens(invocations, "remote", "total_tokens")
    telemetry_status = ("Missing" if not invocations else
                        "Complete" if all(r.get("telemetry_completeness") == "complete"
                                          for r in invocations) else "Partial")
    durations = {}
    for field in ("duration_ns", "prompt_eval_duration", "eval_duration", "load_duration"):
        values = [r[field] for r in invocations if r.get(field) is not None]
        durations[field] = sum(values) if values else None

    result = {
        "task_id": args.task_id,
        "tokens": {"local": local, "remote": remote,
                   "total": local + remote if local is not None and remote is not None else
                   (local if local is not None else remote)},
        "kpis": kpis,
        "durations_ns": durations,
        "task_status": status,
        "telemetry_status": telemetry_status,
        "observed_invocations": len(invocations),
        "baseline_included": any(b.get("task_id") == args.task_id for b in baselines) if args.task_id else bool(baselines),
        "final_response_usage_included": False,
    }
    if args.json:
        print(json.dumps(result, sort_keys=True))
        return

    print("\n**Task Telemetry**")
    print("Tokens | Local | Remote | Total")
    for label, field in (("Input", "input_tokens"), ("Cached input", "cached_input_tokens"),
                         ("Cache writes", "cache_write_tokens"),
                         ("Processing", "processing_tokens"), ("Output", "output_tokens")):
        counts = kpis["breakdown"][field]
        print(f"{label} | {fmt(counts['local'], digits=0)} | {fmt(counts['remote'], digits=0)} | "
              f"{fmt(counts['total'], digits=0)}")
    print(f"Total | {fmt(local, digits=0)} | {fmt(remote, digits=0)} | "
          f"{fmt(result['tokens']['total'], digits=0)}")
    print("Totals include available measurements only; N/A means not measured.")
    if any("processing_tokens" in r.get("derived_fields", []) for r in invocations):
        print("Processing includes derived visible-thinking tokens; hidden or control tokens may be excluded.")
    if any(value is not None for value in durations.values()):
        print("\nDuration (ns) | Observed total")
        for label, field in (("Invocation", "duration_ns"), ("Prompt evaluation", "prompt_eval_duration"),
                             ("Output evaluation", "eval_duration"), ("Model load", "load_duration")):
            print(f"{label} | {fmt(durations[field], digits=0)}")
    print("\nKPI | Value")
    for name in ("RTR", "TDR", "TAF", "RTS", "TSR", "TCR"):
        item = kpis[name]
        value = item["value"]
        if value is None:
            text = f"N/A — {item['reason']}"
        elif name in ("RTR", "TDR", "TSR", "TCR"):
            text = fmt(value, "%")
        elif name == "TAF":
            text = fmt(value, "x")
        else:
            text = str(value)
        print(f"{name} | {text}")
    print(f"- Observed local invocations: {sum(r.get('execution_location') == 'local' for r in invocations)}")
    print(f"- Task status: {status}.")
    print(f"- Telemetry status: {telemetry_status}.")
    print("- Final response usage: Not included.")


if __name__ == "__main__":
    main()
