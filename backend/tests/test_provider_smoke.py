"""The manual live provider smoke script must refuse to send requests until suitability is confirmed."""
import os
from pathlib import Path
import subprocess
import sys


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "smoke_provider_tool_calls.py"
SECRET = "sk-test-secret-value"


def run_smoke(tmp_path, env_lines):
    env_file = tmp_path / ".env"
    env_file.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("MAGIC_RAG_PROVIDER_")}
    return subprocess.run([sys.executable, str(SCRIPT), "--env-file", str(env_file)],
                          cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)


def test_smoke_refuses_without_confirmed_suitability_and_never_prints_the_key(tmp_path):
    result = run_smoke(tmp_path, [
        "MAGIC_RAG_PROVIDER_URL=http://127.0.0.1:9/chat/completions",
        "MAGIC_RAG_PROVIDER_MODEL=test-model",
        f"MAGIC_RAG_PROVIDER_API_KEY={SECRET}",
        "MAGIC_RAG_PROVIDER_SUITABILITY_CONFIRMED=false",
    ])
    assert result.returncode == 2
    assert "suitability" in result.stderr.lower()
    assert SECRET not in result.stdout + result.stderr
