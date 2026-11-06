import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
THRESHOLDS = {"1": 20, "10": 21, "30": 22, "100": 23, "300": 24}


def level_examples():
    example = (ROOT / "tsbot.env.example").read_text(encoding="utf-8")
    lines = []
    for line in example.splitlines():
        if "TSBOT_LEVELS_" in line:
            lines.append(line.removeprefix("# ").replace("TSBOT_LEVELS_ENABLED=false", "TSBOT_LEVELS_ENABLED=true"))
    docs = (ROOT / "docs/levels.md").read_text(encoding="utf-8")
    block = docs.split("```dotenv\n", 1)[1].split("```", 1)[0]
    return {"env example": "\n".join(lines) + "\n", "documentation": block}


def bash_executable():
    if os.name == "nt":
        # Do not pick Windows' WSL launcher: tests need a local Bash shell.
        git = shutil.which("git")
        candidates = [Path(git).resolve().parent.parent / "bin" / "bash.exe"] if git else []
        candidates.append(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe")
        return next((str(path) for path in candidates if path.is_file()), None)
    return shutil.which("bash")


class LevelEnvironmentTests(unittest.TestCase):
    def test_examples_load_through_powershell_importer(self):
        pwsh = shutil.which("pwsh")
        if not pwsh:
            self.skipTest("PowerShell is not installed")
        with tempfile.TemporaryDirectory() as tmp:
            runner = Path(tmp) / "load.ps1"
            runner.write_text(
                'param($Importer, $EnvFile)\n'
                '$ErrorActionPreference = "Stop"\n'
                '. $Importer -Path $EnvFile\n'
                '@{enabled=$env:TSBOT_LEVELS_ENABLED; thresholds=$env:TSBOT_LEVELS_THRESHOLDS} | ConvertTo-Json -Compress\n',
                encoding="utf-8",
            )
            for name, content in level_examples().items():
                with self.subTest(example=name):
                    path = Path(tmp) / "levels.env"
                    path.write_text(content, encoding="utf-8")
                    result = subprocess.run(
                        [pwsh, "-NoProfile", "-File", str(runner),
                         str(ROOT / "scripts/Import-TsbotEnv.ps1"), str(path)],
                        capture_output=True, text=True, encoding="utf-8", check=True,
                    )
                    values = json.loads(result.stdout)
                    self.assertEqual("true", values["enabled"])
                    self.assertEqual(THRESHOLDS, json.loads(values["thresholds"]))

    def test_examples_load_through_compose_env_file(self):
        docker = shutil.which("docker")
        if not docker or subprocess.run([docker, "compose", "version"], capture_output=True).returncode:
            self.skipTest("Docker Compose is not installed")
        with tempfile.TemporaryDirectory() as tmp:
            compose = Path(tmp) / "compose.json"
            compose.write_text(json.dumps({"services": {"probe": {
                "image": "alpine:3", "env_file": ["levels.env"],
            }}}), encoding="utf-8")
            for name, content in level_examples().items():
                with self.subTest(example=name):
                    (Path(tmp) / "levels.env").write_text(content, encoding="utf-8")
                    result = subprocess.run(
                        [docker, "compose", "-p", "levels-config-test", "-f", str(compose), "config", "--format", "json"],
                        capture_output=True, text=True, encoding="utf-8", check=True,
                    )
                    values = json.loads(result.stdout)["services"]["probe"]["environment"]
                    self.assertEqual("true", values["TSBOT_LEVELS_ENABLED"])
                    self.assertEqual(THRESHOLDS, json.loads(values["TSBOT_LEVELS_THRESHOLDS"]))

    def test_examples_export_valid_settings_to_shell_child(self):
        bash = bash_executable()
        if not bash:
            self.skipTest("Bash is not installed")
        env = {key: value for key, value in os.environ.items() if not key.startswith("TSBOT_LEVELS_")}
        with tempfile.TemporaryDirectory() as tmp:
            for name, content in level_examples().items():
                with self.subTest(example=name):
                    path = Path(tmp) / "levels.env"
                    path.write_text(content, encoding="utf-8", newline="\n")
                    result = subprocess.run(
                        [bash, "--noprofile", "--norc", "-c", 'source "$1"; env', "test", path.as_posix()],
                        env=env, capture_output=True, text=True, encoding="utf-8", check=True,
                    )
                    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
                    self.assertEqual("true", values.get("TSBOT_LEVELS_ENABLED"))
                    self.assertEqual(THRESHOLDS, json.loads(values["TSBOT_LEVELS_THRESHOLDS"]))

    def test_examples_keep_valid_json_for_dotenv_loading(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, content in level_examples().items():
                with self.subTest(example=name):
                    path = Path(tmp) / "levels.env"
                    path.write_text(content, encoding="utf-8")
                    values = dotenv_values(path)
                    self.assertEqual("true", values["TSBOT_LEVELS_ENABLED"])
                    self.assertEqual(THRESHOLDS, json.loads(values["TSBOT_LEVELS_THRESHOLDS"]))
