#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kpi import calculate
from telemetry import baselines_file, read_jsonl, telemetry_file


def fmt(value, suffix="", digits=2):
    return "N/A" if value is None else f"{value:.{digits}f}{suffix}"


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
    local_values = [r.get("total_tokens") for r in invocations
                    if r.get("execution_location") == "local" and r.get("total_tokens") is not None]
    remote_values = [r.get("total_tokens") for r in invocations
                     if r.get("execution_location") == "remote" and r.get("total_tokens") is not None]
    local = sum(local_values) if local_values else None
    remote = sum(remote_values) if remote_values else None
    partial = any(r.get("telemetry_completeness") == "partial" for r in invocations)
    missing = not invocations or any(r.get("telemetry_completeness") == "missing" for r in invocations)
    telemetry_status = "Complete" if invocations and not partial and not missing else ("Partial" if invocations else "Missing")

    result = {
        "task_id": args.task_id,
        "tokens": {"local": local, "remote": remote,
                   "total": local + remote if local is not None and remote is not None else
                   (local if local is not None else remote)},
        "kpis": kpis,
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
    print(f"Input | {kpis['breakdown']['input_tokens']['local']} | {kpis['breakdown']['input_tokens']['remote']} | N/A")
    print(f"Processing | {kpis['breakdown']['processing_tokens']['local']} | {kpis['breakdown']['processing_tokens']['remote']} | N/A")
    print(f"Output | {kpis['breakdown']['output_tokens']['local']} | {kpis['breakdown']['output_tokens']['remote']} | N/A")
    print(f"Total | {fmt(local)} | {fmt(remote)} | "
          f"{fmt(local + remote if local is not None and remote is not None else None)}")
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
