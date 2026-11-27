import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import worker as w


class SourceTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.path = Path(td.name) / "record.txt"

    def test_range_skips_large_prefix_and_preserves_physical_lines(self):
        self.path.write_bytes(b"x" * 150000 + b"\r\nquote\r\nend")
        self.assertEqual(w.read_source(self.path, "2:999"), ("quote\r\nend", 2))

    def test_limit_in_utf8_bytes(self):
        self.path.write_bytes(("é" * 2500).encode())
        self.assertEqual(len(w.read_source(self.path)[0]), 2500)
        with self.path.open("ab") as f:
            f.write(b"!")
        for span in [None, "1:1"]:
            with self.subTest(span=span), self.assertRaises(w.JobError):
                w.read_source(self.path, span)

    def test_invalid_ranges(self):
        self.path.write_bytes(b"a\nb")
        for span in ["0:1", "3:4", "2:1", "a", "1:1000000000"]:
            with self.subTest(span=span), self.assertRaises(w.JobError):
                w.read_source(self.path, span)

    def test_invalid_text(self):
        for blob in [b"", b" \n", b"x\0", b"\xff"]:
            self.path.write_bytes(blob)
            with self.subTest(blob=blob), self.assertRaises(w.JobError):
                w.read_source(self.path)


class PortabilityTests(unittest.TestCase):
    def test_worker_from_downloaded_path_and_unrelated_working_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            scripts = root / "Downloaded skill café" / "scripts"
            scripts.mkdir(parents=True)
            downloaded_worker = scripts / "worker.py"
            shutil.copy2(Path(w.__file__).resolve(), downloaded_worker)

            source_dir = root / "source files"
            source_dir.mkdir()
            source = source_dir / "record.txt"
            source.write_bytes(b"first line\nportable line\n")

            unrelated_cwd = root / "unrelated working directory"
            unrelated_cwd.mkdir()
            code = (
                "import importlib.util, json, pathlib, sys\n"
                "spec = importlib.util.spec_from_file_location('downloaded_worker', sys.argv[1])\n"
                "module = importlib.util.module_from_spec(spec)\n"
                "spec.loader.exec_module(module)\n"
                "print(json.dumps(module.read_source(pathlib.Path(sys.argv[2]), '2:2')))\n"
            )
            result = subprocess.run(
                [sys.executable, "-c", code, str(downloaded_worker), str(source)],
                cwd=unrelated_cwd,
                capture_output=True,
                text=True,
                check=True,
            )

            self.assertEqual(result.stdout, '["portable line\\n", 2]\n')


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.schema = w.contract("classify", "outcome?", ["pass", "fail"])

    def test_verified_quotes_and_absolute_line(self):
        obj = {"label": "fail", "quotes": ["error 5"]}
        self.assertEqual(w.verified(obj, self.schema, "ok\nerror 5", 22),
                         {"label": "fail", "evidence": [{"line": 23, "quote": "error 5"}]})

    def test_abstention(self):
        self.assertEqual(w.verified({"label": "unknown", "quotes": []}, self.schema, "x", 1),
                         {"label": "unknown", "evidence": []})

    def test_invalid_results(self):
        for obj in [None, {}, {"quotes": [], "label": "pass"}, {"quotes": ["x"], "label": "unknown"},
                    {"quotes": ["y"], "label": "pass"}, {"quotes": ["x"], "label": "other"},
                    {"quotes": [], "label": "unknown", "extra": "x"}, {"quotes": "x", "label": "pass"},
                    {"quotes": ["x","x"], "label": "pass"}, {"quotes": [["x"]], "label": "pass"}]:
            with self.subTest(obj=obj), self.assertRaises(w.JobError):
                w.verified(obj, self.schema, "x", 1)

    def test_extraction_constraints(self):
        schema = w.contract("extract", "which?", [])
        for value in [["duplicate", "duplicate"], ["z" * 141], [" "], ["a\nb"], list("abcd")]:
            with self.subTest(value=value), self.assertRaises(w.JobError):
                w.verified({"quotes": value}, schema, "duplicate\na\nb\n" + "z" * 141, 1)
        self.assertEqual(w.verified({"quotes": []}, schema, "x", 1), {"evidence": []})

    def test_bad_questions_and_labels(self):
        for kind, q, labels in [("classify", "x", ["a"]), ("classify", "x", ["a", "a"]),
                                ("classify", "x", ["unknown", "b"]), ("classify", "x", ["a", ""]),
                                ("extract", " ", []), ("extract", "é"*181, []), ("extract", "x", ["a"])]:
            with self.subTest(kind=kind, q=q, labels=labels), self.assertRaises(w.JobError):
                w.contract(kind, q, labels)


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.tag = w.MODELS["small"]
        self.tags = {"models": [{"name": self.tag}]}
        self.info = {"details": {"format": "gguf"}}

    def test_missing_model_is_never_implicitly_pulled(self):
        with patch.object(w, "api", return_value={"models": []}) as api, self.assertRaises(w.JobError):
            w.local_model("small")
        self.assertEqual(api.call_count, 1)

    def test_setup_downloads_only_missing_profile(self):
        with patch.object(w, "api", side_effect=[{"models":[]}, {"status":"success"}, self.tags, self.info]) as api:
            self.assertEqual(w.local_model("small", pull=True), self.tag)
            self.assertEqual(api.call_args_list[1].args, ("pull", {"model":self.tag, "stream":False}))
        with patch.object(w, "api", side_effect=[self.tags, self.info]) as api:
            self.assertEqual(w.local_model("small", pull=True), self.tag)
            self.assertEqual([c.args[0] for c in api.call_args_list], ["tags", "show"])

    def test_remote_or_unknown_weights_rejected(self):
        for tags, info in [(self.tags, dict(self.info, remote_host="example")),
                           ({"models":[{"name":self.tag, "remote_model":"elsewhere"}]}, self.info),
                           (self.tags, {"details":{}})]:
            with patch.object(w, "api", side_effect=[tags, info]), self.assertRaises(w.JobError):
                w.local_model("small")

    def test_truncated_and_malformed_output(self):
        for obj in [{"done":False}, {"done":True,"done_reason":"length"},
                    {"done":True,"done_reason":"stop","message":{"content":"oops"}}]:
            with patch.object(w, "api", return_value=obj), self.assertRaises(w.JobError):
                w.infer(self.tag, "extract", "what?", [], "data", 1)

    def test_prompt_budget_after_json_escaping(self):
        with patch.object(w, "api") as api, self.assertRaises(w.JobError):
            w.infer(self.tag, "extract", "what?", [], "\x01" * 4900, 1)
        api.assert_not_called()

    def test_proposal_rejects_incomplete_or_empty_responses(self):
        for answer in [{"done": False}, {"done": True, "done_reason": "length"},
                       {"done": True, "done_reason": "stop", "message": None},
                       {"done": True, "done_reason": "stop", "message": {"content": " "}},
                       {"done": True, "done_reason": "stop", "message": {"content": 7}},
                       {"done": 1, "done_reason": "stop", "message": {"content": "code"}}]:
            with self.subTest(answer=answer), self.assertRaises(w.JobError):
                w.proposal_content(answer)

    def test_proposal_public_entry_point_keeps_source_local(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "source.py"
            path.write_text("private prefix\npass\n")
            answer = {"done": True, "done_reason": "stop", "message": {"content": "def f(): pass"}}
            output = io.StringIO()
            with patch.object(w, "api", side_effect=[self.tags, self.info, answer]) as api, contextlib.redirect_stdout(output):
                status = w.main(["run", "propose", "--file", str(path), "--lines", "2:2",
                                 "--question", "Implement f in a complete file."])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.getvalue()), {"proposal": "def f(): pass"})
            payload = api.call_args.args[1]
            self.assertNotIn("tools", payload)
            self.assertNotIn("private prefix", str(payload))
            self.assertIs(payload["think"], False)

    def test_proposal_input_limits(self):
        with patch.object(w, "api") as api:
            for question, source in [(" ", "source"), ("x" * 1201, "source"),
                                     ("implement", "\x01" * 4900)]:
                with self.subTest(question=question[:20]), self.assertRaises(w.JobError):
                    w.propose(self.tag, question, source)
            api.assert_not_called()

    def test_run_public_entry_point_keeps_source_local(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "build.log"
            path.write_text("private prefix\nFinal run failed with code 7.\n")
            answer = {"done":True, "done_reason":"stop",
                      "message":{"content":'{"label":"failed","quotes":["code 7"]}', "thinking":"private trace"}}
            output = io.StringIO()
            with patch.object(w, "api", side_effect=[self.tags, self.info, answer]) as api, contextlib.redirect_stdout(output):
                status = w.main(["run","classify","--file",str(path),"--lines","2:2","--question","result?",
                                 "--label","passed","--label","failed"])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.getvalue()), {"label":"failed","evidence":[{"line":2,"quote":"code 7"}]})
            payload = api.call_args.args[1]
            self.assertIs(payload["think"], False)
            self.assertNotIn("tools", payload)
            self.assertNotIn("private prefix", str(payload))

    def test_evaluation_requires_correct_meaning(self):
        with patch.object(w, "infer", return_value={"evidence":[]}):
            result = w.evaluate(self.tag)
        self.assertFalse(result["passed"])
        self.assertEqual([r["case"] for r in result["cases"] if r["passed"]], ["absent"])

    def test_evaluation_rejects_distractor_alongside_correct_answer(self):
        def answer(tag, kind, question, labels, source, start):
            return {"evidence":[{"line":2,"quote":"MX49"},{"line":1,"quote":"AX12"}]}
        with patch.object(w,"infer",side_effect=answer):
            cases = w.evaluate(self.tag)["cases"]
            self.assertFalse(next(case for case in cases if case["case"] == "spanish")["passed"])


class TransportTests(unittest.TestCase):
    def test_loopback_transport_and_utf8(self):
        with patch("worker.http.client.HTTPConnection") as ctor:
            response = ctor.return_value.getresponse.return_value
            response.status = 200
            response.read.return_value = b'{"ok":true}'
            self.assertEqual(w.api("chat", {"question":"¿Qué?"}), {"ok":True})
            ctor.assert_called_once_with("127.0.0.1", 11434, timeout=120)
            self.assertEqual(ctor.return_value.request.call_args.args, ("POST","/api/chat"))
            ctor.return_value.close.assert_called_once()

    def test_transport_errors_do_not_echo_response(self):
        for status, raw in [(302,b"private"),(500,b"private"),(200,b"private"),
                            (200,b'{"error":"private"}'),(200,b"x"*(w.MAX_REPLY+1))]:
            conn = MagicMock()
            response = conn.getresponse.return_value
            response.status, response.read.return_value = status, raw
            with patch("worker.http.client.HTTPConnection",return_value=conn), self.assertRaises(w.JobError) as ctx:
                w.api("chat", {})
            self.assertNotIn("private", str(ctx.exception))
            conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
