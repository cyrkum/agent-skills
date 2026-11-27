import os
import subprocess
import tempfile
import unittest
from pathlib import Path


BOOTSTRAP = Path(__file__).resolve().parents[1] / "scripts" / "bootstrap.sh"


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls"
        self.env = {
            **os.environ,
            "HOME": str(self.root),
            "XDG_STATE_HOME": str(self.root / "state"),
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "FAKE_ROOT": str(self.root),
        }
        self.script("uname", 'case "$1" in -n) echo test-host;; -s) echo Linux;; esac')
        self.script("python3", """
echo "python $*" >> "$FAKE_ROOT/calls"
case "$1" in
    -c) test -f "$FAKE_ROOT/python-ready";;
    *) case "$2" in
        doctor) if [ "${FAKE_SERVICE:-ready}" = start ]; then
                    test -f "$FAKE_ROOT/service-ready"
                fi;;
        setup) test ! -f "$FAKE_ROOT/fail-setup";;
        *) exit 1;;
       esac;;
esac
""")
        self.script("apt-get", "exit 0")
        self.script("sudo", """
echo "sudo $*" >> "$FAKE_ROOT/calls"
shift
case "$1" in
    apt-get) touch "$FAKE_ROOT/python-ready";;
    /bin/sh) "$@";;
    *) exit 1;;
esac
""")
        self.script("curl", """
echo "curl $*" >> "$FAKE_ROOT/calls"
cp "$FAKE_ROOT/installer" "$4"
""")
        (self.root / "installer").write_text(
            '#!/bin/sh\ncp "$FAKE_ROOT/ollama" "$FAKE_ROOT/bin/ollama"\n'
        )
        (self.root / "ollama").write_text("#!/bin/sh\nexit 0\n")
        (self.root / "ollama").chmod(0o755)

    def script(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)

    def run_bootstrap(self):
        return subprocess.run(
            ["/bin/sh", str(BOOTSTRAP)], env=self.env,
            capture_output=True, text=True, timeout=15,
        )

    def test_installs_missing_dependencies_and_model(self):
        result = self.run_bootstrap()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.log.read_text()
        self.assertIn("sudo -A apt-get install -y python3", calls)
        self.assertIn("https://ollama.com/install.sh", calls)
        self.assertIn("sudo -A /bin/sh", calls)
        self.assertIn("setup --profile small", calls)
        marker = self.root / "state/delegate-local-tasks/bootstrap-v1-test-host"
        self.assertEqual(marker.read_text(), "complete\n")

    def test_second_use_skips_install_and_dependency_verification(self):
        first = self.run_bootstrap()
        self.assertEqual(first.returncode, 0, first.stderr)
        calls = self.log.read_text()
        second = self.run_bootstrap()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.log.read_text(), calls)

    def test_failed_qualification_does_not_mark_success_and_retries(self):
        (self.root / "fail-setup").touch()
        first = self.run_bootstrap()
        self.assertNotEqual(first.returncode, 0)
        marker = self.root / "state/delegate-local-tasks/bootstrap-v1-test-host"
        self.assertFalse(marker.exists())
        self.assertFalse(Path(str(marker) + ".lock").exists())
        (self.root / "fail-setup").unlink()
        second = self.run_bootstrap()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.log.read_text().count("setup --profile small"), 2)

    def test_existing_dependencies_do_not_install(self):
        (self.root / "python-ready").touch()
        self.script("ollama", "exit 0")
        result = self.run_bootstrap()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.log.read_text()
        self.assertNotIn("sudo ", calls)
        self.assertNotIn("curl ", calls)
        self.assertIn("setup --profile small", calls)

    def test_unsupported_system(self):
        self.script("uname", 'case "$1" in -n) echo test-host;; -s) echo FreeBSD;; esac')
        result = self.run_bootstrap()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unsupported system", result.stderr)
        marker = self.root / "state/delegate-local-tasks/bootstrap-v1-test-host"
        self.assertFalse(marker.exists())
        self.assertFalse(self.log.exists())

    def test_macos_installs_missing_python_with_brew(self):
        self.script("uname", 'case "$1" in -n) echo test-host;; -s) echo Darwin;; esac')
        self.script("ollama", "exit 0")
        self.script("brew", """
echo "brew $*" >> "$FAKE_ROOT/calls"
case "$1" in
    install) touch "$FAKE_ROOT/python-ready";;
    --prefix) echo "$FAKE_ROOT";;
    *) exit 1;;
esac
""")
        result = self.run_bootstrap()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("brew install python", self.log.read_text())
        self.assertIn("setup --profile small", self.log.read_text())

    def test_starts_ollama_when_service_is_unavailable(self):
        (self.root / "python-ready").touch()
        self.env["FAKE_SERVICE"] = "start"
        self.script("ollama", 'touch "$FAKE_ROOT/service-ready"')
        result = self.run_bootstrap()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Starting Ollama", result.stderr)
        self.assertIn("setup --profile small", self.log.read_text())

    def test_existing_lock_prevents_concurrent_installation(self):
        lock = self.root / "state/delegate-local-tasks/bootstrap-v1-test-host.lock"
        lock.mkdir(parents=True)
        result = self.run_bootstrap()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stale lock", result.stderr)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
