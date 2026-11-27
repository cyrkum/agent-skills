import json
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import kpi
import copilot_adapter
import ollama_adapter
import telemetry


def read_fixture(name):
    rows = []
    with (ROOT / "tests" / "fixtures" / name).open() as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


class KpiTests(unittest.TestCase):
    def test_accurate_synthetic_kpis(self):
        records = read_fixture("telemetry.jsonl")
        baselines = read_fixture("baselines.jsonl")
        result = kpi.calculate(records, baselines, "fixture")
        self.assertEqual(result["RTR"]["status"], "unavailable")
        self.assertEqual(result["RTR"]["reason"], "remote token measurement unavailable")
        self.assertEqual(result["TDR"]["status"], "unavailable")
        self.assertEqual(result["TAF"]["status"], "unavailable")
        self.assertEqual(result["RTS"]["status"], "unavailable")
        self.assertEqual(result["TCR"]["value"], 100.0)

    def test_hybrid_kpis(self):
        records = read_fixture("telemetry.jsonl") + [{
            "record_type": "invocation", "task_id": "fixture",
            "execution_location": "remote", "input_tokens": 400,
            "output_tokens": 200, "total_tokens": 600,
            "processing_tokens": None,
        }]
        baselines = read_fixture("baselines.jsonl")
        result = kpi.calculate(records, baselines, "fixture")
        self.assertEqual(result["RTR"]["value"], 40.0)
        self.assertAlmostEqual(result["TDR"]["value"], 20.0)
        self.assertAlmostEqual(result["TAF"]["value"], 0.75)
        self.assertEqual(result["RTS"]["value"], 400)

    def test_missing_division_and_no_tasks(self):
        result = kpi.calculate([], [], None)
        self.assertEqual(result["RTR"]["status"], "unavailable")
        self.assertEqual(result["TSR"]["status"], "unavailable")
        self.assertEqual(result["TCR"]["status"], "unavailable")

    def test_total_derived_from_components_and_zero_baseline(self):
        records = [{"record_type": "invocation", "task_id": "t",
                    "execution_location": "remote", "input_tokens": 10,
                    "output_tokens": 5}]
        result = kpi.calculate(records, [{"task_id": "t", "total_tokens": 0}], "t")
        self.assertEqual(result["TCR"]["value"], 100)
        self.assertEqual(result["RTR"]["status"], "unavailable")

    def test_partial_breakdown_and_measured_zero(self):
        records = [
            {"record_type": "invocation", "execution_location": "local",
             "input_tokens": 0, "output_tokens": 2},
            {"record_type": "invocation", "execution_location": "local",
             "input_tokens": None, "output_tokens": 3},
        ]
        result = kpi.calculate(records)
        inputs = result["breakdown"]["input_tokens"]
        self.assertEqual(inputs["total"], 0)
        self.assertEqual(inputs["status"], "partial")
        self.assertEqual(inputs["measured_invocations"], 1)
        self.assertEqual(inputs["observed_invocations"], 2)
        self.assertEqual(result["TCR"]["value"], 50)


class NormalizationTests(unittest.TestCase):
    def test_native_metadata(self):
        record = telemetry.normalize_invocation({
            "prompt_eval_count": 11,
            "eval_count": 18,
            "total_duration": 174560334,
            "prompt_eval_duration": 100,
            "eval_duration": 200,
            "load_duration": 300,
        }, "task")
        self.assertEqual(record["input_tokens"], 11)
        self.assertEqual(record["output_tokens"], 18)
        self.assertEqual(record["total_tokens"], 29)
        self.assertEqual(record["duration_ns"], 174560334)
        self.assertEqual(record["prompt_eval_duration"], 100)
        self.assertEqual(record["eval_duration"], 200)
        self.assertEqual(record["load_duration"], 300)
        self.assertIn("prompt_eval_duration", record["measured_fields"])
        self.assertEqual(record["telemetry_completeness"], "complete")

    def test_partial_metadata(self):
        record = telemetry.normalize_invocation({"eval_count": 18}, "task")
        self.assertIsNone(record["input_tokens"])
        self.assertEqual(record["output_tokens"], 18)
        self.assertEqual(record["telemetry_completeness"], "partial")

    def test_measured_generic_usage_and_derived_output(self):
        record = telemetry.normalize_invocation({
            "input_tokens": 11, "total_tokens": 29, "processing_tokens": 4,
            "cached_input_tokens": 3,
        }, "task", provider="example", location="remote", telemetry_source="manual_measured")
        self.assertEqual(record["input_tokens"], 11)
        self.assertEqual(record["output_tokens"], 18)
        self.assertEqual(record["total_tokens"], 29)
        self.assertEqual(record["processing_tokens"], 4)
        self.assertEqual(record["cached_input_tokens"], 3)
        self.assertNotIn("output_tokens", record["measured_fields"])

    def test_missing_counts_are_not_invented(self):
        record = telemetry.normalize_invocation({"total_tokens": 29}, "task")
        self.assertEqual(record["total_tokens"], 29)
        self.assertIsNone(record["input_tokens"])
        self.assertIsNone(record["processing_tokens"])
        self.assertIsNone(record["output_tokens"])

    def test_ollama_cached_prompt_count(self):
        record = telemetry.normalize_invocation({
            "prompt_eval_count": 40, "prompt_eval_cached_count": 12,
            "eval_count": 5,
        }, "task")
        self.assertEqual(record["cached_input_tokens"], 12)
        self.assertEqual(record["total_tokens"], 45)
        self.assertIn("cached_input_tokens", record["measured_fields"])


class ReasoningTokenTests(unittest.TestCase):
    def test_exact_alignment_counts_tokens_not_chunks_or_words(self):
        logprobs = [{"token": t} for t in ("<think>", "reason", "ing", " text", "</think>", "answer")]
        self.assertEqual(ollama_adapter.reasoning_token_count("reasoning text", logprobs, 6), 3)

    def test_rejects_ambiguous_partial_or_missing_token_evidence(self):
        for thinking, tokens, count in (
            ("reason", ["reason", "reason"], 2),
            ("son", ["reason"], 1),
            ("reason", ["reason", "other"], 1),
            ("reasoning", ["reason"], 2),
            ("", ["reason"], 1),
            ("reason", ["reason", ""], 2),
        ):
            self.assertIsNone(ollama_adapter.reasoning_token_count(
                thinking, [{"token": token} for token in tokens], count))

    def test_end_token_can_be_counted_without_a_logprob(self):
        self.assertEqual(ollama_adapter.reasoning_token_count(
            "reason", [{"token": "reason"}, {"token": "answer"}], 3), 1)


class CopilotAdapterTests(unittest.TestCase):
    @staticmethod
    def session_usage(event_id, inputs, outputs, cached, provider=None):
        return {
            "type": "session.usage_record", "id": event_id,
            "timestamp": "2026-11-27T23:12:25.933Z",
            "data": {"usage": {
                "model": "gpt-6.1-terra",
                "provider": provider or {"id": "copilot", "kind": "copilot"},
                "isByok": False, "inputTokens": inputs, "outputTokens": outputs,
                "cacheReadTokens": cached, "cacheWriteTokens": 1,
                "reasoningTokens": 2, "duration": 5,
            }},
        }

    def test_import_scoped_session_usage_and_report_idempotently(self):
        events = [
            {"type": "user.message", "id": "first"},
            self.session_usage("one", 100, 10, 90),
            {"type": "user.message", "id": "second"},
            self.session_usage("two", 200, 20, 180),
            self.session_usage("three", 300, 30, 250),
        ]
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"TOKEN_TELEMETRY_DIR": temp}):
            path = Path(temp) / "events.jsonl"
            path.write_text("".join(json.dumps(event) + "\n" for event in events))
            self.assertEqual(copilot_adapter.import_session_usage(path, "demo"), 2)
            self.assertEqual(copilot_adapter.import_session_usage(path, "demo"), 0)
            records = telemetry.read_jsonl(telemetry.telemetry_file())
            self.assertEqual([r["invocation_id"] for r in records], ["two", "three"])
            self.assertEqual(records[0]["duration_ns"], 5_000_000)
            output = subprocess.run(
                [sys.executable, str(SCRIPTS / "report.py"), "--task-id", "demo"],
                check=True, capture_output=True, text=True).stdout
            self.assertIn("Input | N/A | 500 | 500", output)
            self.assertIn("Cached input | N/A | 430 | 430", output)
            self.assertIn("Output | N/A | 50 | 50", output)
            self.assertIn("Total | N/A | 550 | 550", output)
            self.assertIn("Final response usage: Unknown", output)
            self.assertEqual(copilot_adapter.import_session_usage(path, "first-task", "first"), 1)
            with self.assertRaisesRegex(ValueError, "another task"):
                copilot_adapter.import_session_usage(path, "other")

    def test_import_rejects_unknown_provider_without_partial_writes(self):
        events = [
            {"type": "user.message", "id": "first"},
            self.session_usage("one", 100, 10, 90),
            self.session_usage("two", 100, 10, 90, {"kind": "unknown"}),
        ]
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"TOKEN_TELEMETRY_DIR": temp}):
            path = Path(temp) / "events.jsonl"
            path.write_text("".join(json.dumps(event) + "\n" for event in events))
            with self.assertRaisesRegex(ValueError, "execution location"):
                copilot_adapter.import_session_usage(path, "demo")
            self.assertFalse(telemetry.telemetry_file().exists())
            with self.assertRaisesRegex(ValueError, "user message not found"):
                copilot_adapter.import_session_usage(path, "demo", "missing")

    def test_import_cli_resolves_session_and_reports_missing_usage(self):
        with tempfile.TemporaryDirectory() as temp:
            session = Path(temp) / "session-state" / "session-id"
            session.mkdir(parents=True)
            (session / "events.jsonl").write_text(
                json.dumps({"type": "user.message", "id": "message"}) + "\n" +
                json.dumps(self.session_usage("one", 100, 10, 90)) + "\n")
            env = dict(os.environ, TOKEN_TELEMETRY_DIR=temp, COPILOT_HOME=temp,
                       COPILOT_AGENT_SESSION_ID="session-id")
            command = [sys.executable, str(SCRIPTS / "copilot_adapter.py"), "--task-id", "demo"]
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Imported 1", result.stdout)
            (session / "events.jsonl").write_text(json.dumps({"type": "user.message", "id": "message"}) + "\n")
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no usage records", result.stderr)

    def test_usage_event_records_sdk_counts_without_double_counting_cache(self):
        data = SimpleNamespace(model="m", input_tokens=100, output_tokens=30,
                               cache_read_tokens=20, cache_write_tokens=10,
                               reasoning_tokens=12, duration=timedelta(milliseconds=5),
                               model_provider="openai")
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"TOKEN_TELEMETRY_DIR": temp}):
            copilot_adapter.record_usage(data, "demo", location="remote")
            record = telemetry.read_jsonl(telemetry.telemetry_file())[0]
            self.assertEqual(record["input_tokens"], 100)
            self.assertEqual(record["output_tokens"], 30)
            self.assertEqual(record["total_tokens"], 130)
            self.assertEqual(record["cached_input_tokens"], 20)
            self.assertEqual(record["cache_write_tokens"], 10)
            self.assertEqual(record["processing_tokens"], 12)
            self.assertEqual(record["duration_ns"], 5_000_000)
            self.assertEqual(record["telemetry_source"], "copilot_sdk_usage")
            output = subprocess.run(
                [sys.executable, str(SCRIPTS / "report.py"), "--task-id", "demo"],
                check=True, capture_output=True, text=True).stdout
            self.assertIn("Cached input | N/A | 20 | 20", output)
            self.assertIn("Cache writes | N/A | 10 | 10", output)
            self.assertIn("Processing | N/A | 12 | 12", output)
            self.assertIn("Total | N/A | 130 | 130", output)

    def test_missing_and_invalid_usage_are_not_fabricated_or_recorded(self):
        data = SimpleNamespace(model="m", input_tokens=10, output_tokens=None,
                               cache_read_tokens=None, reasoning_tokens=None, duration=None,
                               model_provider=None)
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"TOKEN_TELEMETRY_DIR": temp}):
            copilot_adapter.record_usage(data, "demo", location="remote")
            record = telemetry.read_jsonl(telemetry.telemetry_file())[0]
            self.assertIsNone(record["processing_tokens"])
            self.assertIsNone(record["total_tokens"])
            data.reasoning_tokens = -1
            with self.assertRaises(ValueError):
                copilot_adapter.record_usage(data, "demo", location="remote")
            self.assertEqual(len(telemetry.read_jsonl(telemetry.telemetry_file())), 1)

    def test_usage_must_specify_location_and_consistent_counts(self):
        data = SimpleNamespace(model="m", input_tokens=10, output_tokens=5,
                               cache_read_tokens=8, cache_write_tokens=3,
                               reasoning_tokens=1)
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"TOKEN_TELEMETRY_DIR": temp}):
            with self.assertRaises(ValueError):
                copilot_adapter.record_usage(data, "demo", location="unknown")
            with self.assertRaises(ValueError):
                copilot_adapter.record_usage(data, "demo", location="remote")
            self.assertFalse(telemetry.telemetry_file().exists())


class ScriptTests(unittest.TestCase):
    def test_non_streaming_reasoning_is_counted(self):
        response = {
            "done": True, "thinking": "abc def", "response": "answer",
            "logprobs": [{"token": "abc"}, {"token": " def"}, {"token": "answer"}],
            "prompt_eval_count": 8, "eval_count": 3,
        }
        with tempfile.TemporaryDirectory() as temp:
            args = ["ollama_adapter.py", "generate", "--task-id", "demo", "--model", "m",
                    "--prompt", "test", "--count-reasoning"]
            with patch.dict(os.environ, {"TOKEN_TELEMETRY_DIR": temp}), \
                 patch.object(sys, "argv", args), \
                 patch.object(ollama_adapter, "post", return_value=json.dumps(response).encode()), \
                 redirect_stdout(io.StringIO()):
                self.assertEqual(ollama_adapter.main(), 0)
            record = json.loads((Path(temp) / "telemetry.jsonl").read_text())
            self.assertEqual(record["processing_tokens"], 2)

    def test_streamed_thinking_and_logprobs_are_aggregated_privately(self):
        events = [
            {"message": {"thinking": "private "}, "logprobs": [{"token": "private "}]},
            {"message": {"thinking": "thinking"}, "logprobs": [{"token": "thinking"}]},
            {"message": {"content": "answer"}, "logprobs": [{"token": "answer"}]},
            {"done": True, "prompt_eval_count": 8, "prompt_eval_cached_count": 3,
             "eval_count": 3, "total_duration": 99},
        ]
        body = b"\n".join(json.dumps(event).encode() for event in events)
        with tempfile.TemporaryDirectory() as temp:
            args = ["ollama_adapter.py", "chat", "--task-id", "demo", "--model", "m",
                    "--message", "private prompt", "--stream", "--count-reasoning"]
            with patch.dict(os.environ, {"TOKEN_TELEMETRY_DIR": temp}), \
                 patch.object(sys, "argv", args), \
                 patch.object(ollama_adapter, "post", return_value=body) as post, \
                 redirect_stdout(io.StringIO()):
                self.assertEqual(ollama_adapter.main(), 0)
            self.assertTrue(post.call_args.args[1]["logprobs"])
            saved = (Path(temp) / "telemetry.jsonl").read_text()
            self.assertNotIn("private", saved)
            record = json.loads(saved)
            self.assertEqual(record["processing_tokens"], 2)
            self.assertEqual(record["cached_input_tokens"], 3)
            self.assertIn("processing_tokens", record["derived_fields"])
            self.assertNotIn("processing_tokens", record["measured_fields"])
            output = subprocess.run(
                [sys.executable, str(SCRIPTS / "report.py"), "--task-id", "demo"],
                env={**os.environ, "TOKEN_TELEMETRY_DIR": temp},
                check=True, capture_output=True, text=True).stdout
            self.assertIn("Processing | 2 | N/A | 2", output)
            self.assertIn("derived visible-thinking tokens", output)
            output_json = subprocess.run(
                [sys.executable, str(SCRIPTS / "report.py"), "--task-id", "demo", "--json"],
                env={**os.environ, "TOKEN_TELEMETRY_DIR": temp},
                check=True, capture_output=True, text=True).stdout
            self.assertEqual(json.loads(output_json)["kpis"]["breakdown"]["processing_tokens"]
                             ["derived_invocations"], 1)

    def test_streamed_ollama_usage_is_saved_without_response_content(self):
        events = [
            {"response": "private text", "done": False},
            {"done": True, "prompt_eval_count": 8, "eval_count": 4,
             "total_duration": 99, "prompt_eval_duration": 10,
             "eval_duration": 20, "load_duration": 30},
        ]
        body = b"\n".join(json.dumps(event).encode() for event in events)
        with tempfile.TemporaryDirectory() as temp:
            args = ["ollama_adapter.py", "generate", "--task-id", "demo",
                    "--model", "m", "--prompt", "private prompt", "--stream"]
            with patch.dict(os.environ, {"TOKEN_TELEMETRY_DIR": temp}), \
                 patch.object(sys, "argv", args), \
                 patch.object(ollama_adapter, "post", return_value=body), \
                 redirect_stdout(io.StringIO()):
                self.assertEqual(ollama_adapter.main(), 0)
            saved = (Path(temp) / "telemetry.jsonl").read_text()
            self.assertNotIn("private", saved)
            record = json.loads(saved)
            self.assertEqual(record["total_tokens"], 12)
            self.assertEqual(record["prompt_eval_duration"], 10)
            self.assertEqual(record["eval_duration"], 20)
            self.assertEqual(record["load_duration"], 30)

    def test_record_and_report_measured_usage(self):
        env = dict(__import__("os").environ)
        with tempfile.TemporaryDirectory() as temp:
            env["TOKEN_TELEMETRY_DIR"] = temp
            command = [sys.executable, str(SCRIPTS / "telemetry.py"), "record",
                       "--task-id", "demo", "--provider", "example", "--model", "m",
                       "--location", "remote", "--input-tokens", "40",
                       "--output-tokens", "15", "--processing-tokens", "5",
                       "--cached-input-tokens", "12", "--duration-ns", "100"]
            subprocess.run(command, env=env, check=True, capture_output=True, text=True)
            report = subprocess.run([sys.executable, str(SCRIPTS / "report.py"),
                                     "--task-id", "demo"],
                                    env=env, check=True, capture_output=True, text=True).stdout
            self.assertIn("Input | N/A | 40 | 40", report)
            self.assertIn("Processing | N/A | 5 | 5", report)
            self.assertIn("Cached input | N/A | 12 | 12", report)
            self.assertIn("Output | N/A | 15 | 15", report)
            self.assertIn("Total | N/A | 55 | 55", report)
            self.assertIn("Invocation | 100", report)
            self.assertNotIn("None", report)

    def test_hybrid_report_and_legacy_derived_totals(self):
        env = dict(__import__("os").environ)
        with tempfile.TemporaryDirectory() as temp:
            env["TOKEN_TELEMETRY_DIR"] = temp
            path = Path(temp) / "telemetry.jsonl"
            for location, input_count, output_count in (("local", 10, 4), ("remote", 20, 6)):
                telemetry.append_record(path, {
                    "record_type": "invocation", "task_id": "demo",
                    "execution_location": location, "input_tokens": input_count,
                    "output_tokens": output_count, "telemetry_completeness": "partial",
                })
            output = subprocess.run([sys.executable, str(SCRIPTS / "report.py"),
                                     "--task-id", "demo", "--json"],
                                    env=env, check=True, capture_output=True, text=True).stdout
            report = json.loads(output)
            self.assertEqual(report["tokens"], {"local": 14, "remote": 26, "total": 40})
            self.assertEqual(report["kpis"]["breakdown"]["input_tokens"]["total"], 30)
            self.assertEqual(report["kpis"]["breakdown"]["output_tokens"]["total"], 10)
            self.assertEqual(report["telemetry_status"], "Partial")

    def test_record_rejects_inconsistent_or_invalid_counts(self):
        env = dict(__import__("os").environ)
        with tempfile.TemporaryDirectory() as temp:
            env["TOKEN_TELEMETRY_DIR"] = temp
            base = [sys.executable, str(SCRIPTS / "telemetry.py"), "record",
                    "--task-id", "demo", "--provider", "example", "--model", "m",
                    "--location", "remote"]
            for args in (["--input-tokens", "-1"],
                         ["--input-tokens", "10", "--output-tokens", "5", "--total-tokens", "99"],
                         ["--input-tokens", "10", "--total-tokens", "5"],
                         ["--output-tokens", "5", "--processing-tokens", "6"],
                         ["--total-tokens", "5", "--cached-input-tokens", "6"],
                         ["--total-tokens", "5", "--cached-input-tokens", "3",
                          "--processing-tokens", "3"],
                         []):
                result = subprocess.run(base + args, env=env, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(result.stderr)
            self.assertFalse((Path(temp) / "telemetry.jsonl").exists())

    def test_report_without_baseline(self):
        env = dict(__import__("os").environ)
        with tempfile.TemporaryDirectory() as temp:
            env["TOKEN_TELEMETRY_DIR"] = temp
            subprocess.run([sys.executable, str(SCRIPTS / "telemetry.py"),
                            "init", "--task-id", "demo"], env=env, check=True)
            result = subprocess.run([sys.executable, str(SCRIPTS / "report.py"),
                                     "--task-id", "demo", "--json"],
                                    env=env, check=True, capture_output=True, text=True)
            report = json.loads(result.stdout)
            self.assertEqual(report["telemetry_status"], "Missing")
            self.assertEqual(report["kpis"]["RTR"]["status"], "unavailable")

    def test_vscode_chat_report_markdown_for_task_lifecycle(self):
        with tempfile.TemporaryDirectory() as temp:
            env = {**os.environ, "TOKEN_TELEMETRY_DIR": temp}
            telemetry_cli = [sys.executable, str(SCRIPTS / "telemetry.py")]
            for args in (
                ["init", "--task-id", "demo"],
                ["record", "--task-id", "demo", "--provider", "example", "--model", "m",
                 "--location", "remote", "--input-tokens", "40", "--output-tokens", "15",
                 "--duration-ns", "100"],
                ["finalize", "--task-id", "demo", "--status", "passed"],
            ):
                subprocess.run(telemetry_cli + args, env=env, check=True, capture_output=True, text=True)
            report = subprocess.run(
                [sys.executable, str(SCRIPTS / "report.py"), "--task-id", "demo"],
                env=env, check=True, capture_output=True, text=True).stdout

            self.assertIn("**Task Telemetry**\n\nTokens | Local | Remote | Total\n"
                          "--- | --- | --- | ---\n", report)
            self.assertIn("Total | N/A | 55 | 55\n\n", report)
            self.assertIn("Duration (ns) | Observed total\n--- | ---\nInvocation | 100", report)
            self.assertIn("KPI | Value\n--- | ---\n", report)
            self.assertIn("\n\n- Observed local invocations: 0", report)
            self.assertIn("- Task status: passed.", report)
            self.assertIn("- Final response usage: Not included.", report)

    def test_vscode_chat_report_without_invocations(self):
        with tempfile.TemporaryDirectory() as temp:
            env = {**os.environ, "TOKEN_TELEMETRY_DIR": temp}
            report = subprocess.run(
                [sys.executable, str(SCRIPTS / "report.py"), "--task-id", "missing"],
                env=env, check=True, capture_output=True, text=True).stdout
            self.assertIn("Input | N/A | N/A | N/A", report)
            self.assertIn("KPI | Value\n--- | ---\n", report)
            self.assertNotIn("Duration (ns)", report)
            self.assertIn("- Telemetry status: Missing.", report)

    def test_install_idempotency(self):
        with tempfile.TemporaryDirectory() as temp:
            command = [str(SCRIPTS / "install.sh"), "--source", str(ROOT),
                       "--agents-home", temp]
            subprocess.run(command, check=True)
            subprocess.run(command, check=True)
            link = Path(temp) / "skills" / "token-telemetry"
            self.assertTrue(link.is_symlink())
            subprocess.run([str(SCRIPTS / "uninstall.sh"), "--agents-home", temp], check=True)
            self.assertFalse(link.exists())


if __name__ == "__main__":
    unittest.main()
