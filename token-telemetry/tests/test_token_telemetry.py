import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import kpi
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


class NormalizationTests(unittest.TestCase):
    def test_native_metadata(self):
        record = telemetry.normalize_invocation({
            "prompt_eval_count": 11,
            "eval_count": 18,
            "total_duration": 174560334,
        }, "task")
        self.assertEqual(record["input_tokens"], 11)
        self.assertEqual(record["output_tokens"], 18)
        self.assertEqual(record["total_tokens"], 29)
        self.assertEqual(record["duration_ns"], 174560334)
        self.assertEqual(record["telemetry_completeness"], "complete")

    def test_partial_metadata(self):
        record = telemetry.normalize_invocation({"eval_count": 18}, "task")
        self.assertIsNone(record["input_tokens"])
        self.assertEqual(record["output_tokens"], 18)
        self.assertEqual(record["telemetry_completeness"], "partial")


class ScriptTests(unittest.TestCase):
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
