"""Exercise the read-only audit CLI using saved GitHub-shaped responses."""
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_issue_handoff.py"
PR_URL = "https://github.com/George713/magic-rag/pull/13"
ISSUE_URL = "https://github.com/George713/magic-rag/issues/2"


@pytest.fixture
def snapshot():
    return {"pr": {"number": 13, "url": PR_URL, "state": "OPEN", "isDraft": False,
                   "closingIssuesReferences": [{"number": 2, "url": ISSUE_URL}]},
            "issues": [{"number": 2, "url": ISSUE_URL, "state": "OPEN",
                        "labels": [{"name": "ready-for-human"}, {"name": "backend"}],
                        "body": f"## Implementation status\nReady for review in [PR #13]({PR_URL}).\n\n"
                                "## Verification evidence\n[API test results](https://example.test/results).\n\n"
                                "## Acceptance criteria\n- [x] Search returns the card.\n"}]}


def run_audit(tmp_path, snapshot):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), "--snapshot", str(path), "--json"],
                            cwd=tmp_path, capture_output=True, text=True)
    return result.returncode, json.loads(result.stdout)


def test_handoff_audit_passes_review_ready_work_without_mutating_the_snapshot(tmp_path, snapshot):
    before = copy.deepcopy(snapshot)
    code, report = run_audit(tmp_path, snapshot)
    assert code == 0
    assert report == {"status": "pass", "pr_url": PR_URL, "checked_issues": 1, "errors": []}
    assert json.loads((tmp_path / "snapshot.json").read_text()) == before


@pytest.mark.parametrize("roles", [["ready-for-agent"], ["ready-for-human", "needs-info"], []])
def test_handoff_audit_rejects_stale_missing_or_conflicting_triage_roles(tmp_path, snapshot, roles):
    snapshot["issues"][0]["labels"] = [{"name": name} for name in roles]
    code, report = run_audit(tmp_path, snapshot)
    assert code == 1
    assert "expected only ready-for-human" in report["errors"][0]


@pytest.mark.parametrize("reason", ["**Blocked:** waiting for provider workload approval.", "Deferred: approved follow-up in #15."])
def test_handoff_audit_preserves_explicitly_explained_unfinished_work(tmp_path, snapshot, reason):
    snapshot["issues"][0]["body"] += f"- [ ] Run the live provider smoke. {reason}\n"
    assert run_audit(tmp_path, snapshot)[0] == 0


def test_handoff_audit_rejects_unexplained_unchecked_criteria(tmp_path, snapshot):
    snapshot["issues"][0]["body"] += "- [ ] Run the live provider smoke.\n"
    code, report = run_audit(tmp_path, snapshot)
    assert code == 1
    assert "unchecked criterion" in report["errors"][0]


def test_handoff_audit_ignores_checkbox_examples_in_code_fences(tmp_path, snapshot):
    snapshot["issues"][0]["body"] += "\n## Example syntax\n```markdown\n- [ ] Example, not an acceptance criterion.\n```\n"
    assert run_audit(tmp_path, snapshot)[0] == 0


def test_handoff_audit_distinguishes_same_number_in_different_repositories(tmp_path, snapshot):
    other = copy.deepcopy(snapshot["issues"][0])
    other["url"] = "https://github.com/another/project/issues/2"
    snapshot["issues"].append(other)
    snapshot["pr"]["closingIssuesReferences"].append({"number": 2, "url": other["url"]})
    code, report = run_audit(tmp_path, snapshot)
    assert code == 0 and report["checked_issues"] == 2


@pytest.mark.parametrize("body", ["", f"## Implementation status\n{PR_URL}\n",
                                  "## Implementation status\nhttps://github.com/George713/magic-rag/pull/130\n"
                                  "## Verification evidence\nhttps://example.test/results\n"])
def test_handoff_audit_rejects_missing_status_evidence_or_the_wrong_pr(tmp_path, snapshot, body):
    snapshot["issues"][0]["body"] = body
    assert run_audit(tmp_path, snapshot)[0] == 1


def test_handoff_audit_accepts_existing_inline_evidence_format(tmp_path, snapshot):
    snapshot["issues"][0]["body"] = f"## Implementation status\n[PR]({PR_URL})\n\nImplementation and verification evidence: [documentation](https://example.test/docs).\n"
    assert run_audit(tmp_path, snapshot)[0] == 0


def test_handoff_audit_runs_before_a_draft_is_marked_ready(tmp_path, snapshot):
    snapshot["pr"]["isDraft"] = True
    snapshot["issues"][0]["labels"] = [{"name": "ready-for-agent"}]
    assert run_audit(tmp_path, snapshot)[0] == 1


def test_handoff_audit_reports_missing_issue_data_and_missing_closing_links(tmp_path, snapshot):
    snapshot["issues"] = []
    code, report = run_audit(tmp_path, snapshot)
    assert code == 1 and "Issue data missing" in report["errors"][0]
    snapshot["pr"]["closingIssuesReferences"] = []
    code, report = run_audit(tmp_path, snapshot)
    assert code == 1 and "no closing issue links" in report["errors"][0]


def test_handoff_audit_handles_already_closed_work(tmp_path, snapshot):
    snapshot["issues"][0]["state"] = "CLOSED"
    snapshot["issues"][0]["labels"] = []
    assert run_audit(tmp_path, snapshot)[0] == 0


def test_handoff_audit_fails_closed_on_bad_input(tmp_path):
    code, report = run_audit(tmp_path, {"pr": {}, "issues": []})
    assert code == 2
    assert report["status"] == "error"
