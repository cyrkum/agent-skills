import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
INSTALLER = REPOSITORY / "install-skills.sh"
SKILLS = sorted(
    path.parent for path in REPOSITORY.glob("*/SKILL.md") if path.is_file()
)


class InstallSkillsTests(unittest.TestCase):
    def run_installer(self, *args, cwd=None, env=None):
        return subprocess.run(
            [str(INSTALLER), *map(str, args)],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_defaults_to_agents_home_under_home(self):
        self.assertTrue(SKILLS, "Expected at least one repository skill")
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            result = self.run_installer(
                cwd=home, env={**os.environ, "HOME": str(home)}
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            for skill in SKILLS:
                link = home / ".agents" / "skills" / skill.name
                self.assertTrue(link.is_symlink())
                self.assertEqual(link.resolve(), skill.resolve())

    def test_installs_all_skills_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            agents_home = Path(temporary) / "agents home"
            result = self.run_installer("--agents-home", agents_home)
            self.assertEqual(result.returncode, 0, result.stderr)

            for skill in SKILLS:
                link = agents_home / "skills" / skill.name
                self.assertTrue(link.is_symlink())
                self.assertEqual(link.resolve(), skill.resolve())

            repeated = self.run_installer("--agents-home", agents_home)
            self.assertEqual(repeated.returncode, 0, repeated.stderr)

    def test_handles_repository_path_with_spaces(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "repository with spaces"
            skill = repository / "example-skill"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: example-skill\n---\n")
            installer = repository / "install-skills.sh"
            shutil.copy2(INSTALLER, installer)

            agents_home = Path(temporary) / "agents home"
            result = subprocess.run(
                [str(installer), "--agents-home", str(agents_home)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            link = agents_home / "skills" / "example-skill"
            self.assertEqual(link.resolve(), skill.resolve())

    def test_installs_only_the_requested_skill(self):
        self.assertTrue(SKILLS, "Expected at least one repository skill")
        with tempfile.TemporaryDirectory() as temporary:
            agents_home = Path(temporary) / "agents"
            result = self.run_installer(SKILLS[0].name, "--agents-home", agents_home)
            self.assertEqual(result.returncode, 0, result.stderr)

            links = list((agents_home / "skills").iterdir())
            self.assertEqual([link.name for link in links], [SKILLS[0].name])
            self.assertEqual(links[0].resolve(), SKILLS[0].resolve())

    def test_rejects_unknown_skill(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_installer(
                "missing-skill", "--agents-home", Path(temporary) / "agents"
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Unknown skill", result.stderr)

    def test_does_not_replace_existing_destination(self):
        self.assertTrue(SKILLS, "Expected at least one repository skill")
        with tempfile.TemporaryDirectory() as temporary:
            agents_home = Path(temporary) / "agents"
            destination = agents_home / "skills" / SKILLS[0].name
            destination.parent.mkdir(parents=True)
            destination.write_text("preserve this file")

            result = self.run_installer(
                SKILLS[0].name, "--agents-home", agents_home
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(destination.read_text(), "preserve this file")

    def test_does_not_replace_existing_symlink(self):
        self.assertTrue(SKILLS, "Expected at least one repository skill")
        with tempfile.TemporaryDirectory() as temporary:
            agents_home = Path(temporary) / "agents"
            destination = agents_home / "skills" / SKILLS[0].name
            destination.parent.mkdir(parents=True)
            other_target = Path(temporary) / "other-skill"
            other_target.mkdir()
            destination.symlink_to(other_target, target_is_directory=True)

            result = self.run_installer(
                SKILLS[0].name, "--agents-home", agents_home
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(destination.resolve(), other_target.resolve())

    def test_rejects_skill_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_installer(
                "../README.md", "--agents-home", Path(temporary) / "agents"
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Invalid skill name", result.stderr)


if __name__ == "__main__":
    unittest.main()
