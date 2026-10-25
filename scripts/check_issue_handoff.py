"""Read-only audit of the issues a pull request will close."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TRIAGE_LABELS = {"needs-triage", "needs-info", "ready-for-agent", "ready-for-human", "wontfix"}


def section(body, title):
    heading = re.search(rf"(?im)^##[ \t]+{re.escape(title)}[ \t]*\r?$", body)
    if not heading:
        return ""
    tail = body[heading.end():]
    following = re.search(r"(?m)^#{1,2}[ \t]+", tail)
    return tail[:following.start()] if following else tail


def audit(snapshot):
    pr, issues = snapshot["pr"], snapshot["issues"]
    if not isinstance(pr, dict) or not isinstance(issues, list):
        raise ValueError("Snapshot needs a pr object and an issues list.")
    if pr["state"] != "OPEN":
        return ["Handoff auditing applies to an open draft or review-ready PR."]
    pr_url = pr["url"].rstrip("/")
    references = pr["closingIssuesReferences"]
    if not references:
        return ["PR has no closing issue links. Link the tracked work before handoff."]
    by_url = {issue["url"].rstrip("/"): issue for issue in issues}
    if len(by_url) != len(issues):
        raise ValueError("Snapshot contains duplicate issue URLs.")
    errors = []
    for reference in references:
        issue = by_url.get(reference["url"].rstrip("/"))
        if issue is None:
            errors.append(f"Issue data missing for {reference['url']}.")
            continue
        label = f"Issue #{issue['number']}"
        if issue["state"] == "CLOSED":
            continue
        if issue["state"] != "OPEN":
            errors.append(f"{label}: unknown issue state.")
            continue
        roles = {item["name"] for item in issue["labels"]} & TRIAGE_LABELS
        if roles != {"ready-for-human"}:
            errors.append(f"{label}: expected only ready-for-human as triage role; found {', '.join(sorted(roles)) or 'none'}.")
        body = issue["body"]
        status = section(body, "Implementation status")
        if not status.strip():
            errors.append(f"{label}: missing Implementation status section.")
        elif not re.search(re.escape(pr_url) + r"(?=$|[\s)#/?])", status):
            errors.append(f"{label}: Implementation status must link this PR.")
        evidence = section(body, "Verification evidence")
        if not evidence:
            inline = re.search(r"(?im)^(?:Implementation and )?Verification evidence:[ \t]*(.+)$", body)
            evidence = inline.group(1) if inline else ""
        urls = {url.rstrip("/.,;") for url in re.findall(r"https?://[^\s<>)]+", evidence)}
        if not urls - {pr_url}:
            errors.append(f"{label}: add verification evidence links beyond the PR overview.")
        fence = None
        for line_number, line in enumerate(body.splitlines(), 1):
            marker = re.match(r"^\s*(`{3,}|~{3,})", line)
            if marker:
                token = marker.group(1)
                if fence is None:
                    fence = token
                elif token[0] == fence[0] and len(token) >= len(fence):
                    fence = None
                continue
            if fence:
                continue
            if re.match(r"^\s*[-*]\s+\[ \]", line) and not re.search(r"\b(?:Blocked|Deferred):(?:\*\*)?[ \t]+\S", line, re.IGNORECASE):
                errors.append(f"{label}: unchecked criterion on line {line_number} needs a Blocked: or Deferred: explanation.")
    return errors


def gh_json(arguments):
    result = subprocess.run(["gh", *arguments], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True, timeout=60)
    return json.loads(result.stdout)


def fetch_snapshot(number, repo):
    arguments = ["pr", "view", str(number), "--json", "number,url,state,isDraft,closingIssuesReferences"]
    if repo:
        arguments.extend(["--repo", repo])
    pr = gh_json(arguments)
    issues = [gh_json(["issue", "view", reference["url"], "--json", "number,url,state,labels,body"])
              for reference in pr["closingIssuesReferences"]]
    return {"pr": pr, "issues": issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pr", type=int, help="Open PR number, including a draft being prepared for review.")
    source.add_argument("--snapshot", type=Path, help="Audit saved {pr, issues} JSON without GitHub access.")
    parser.add_argument("--repo", help="Optional OWNER/REPO for --pr; otherwise use this checkout's remote.")
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable result.")
    args = parser.parse_args()
    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8-sig")) if args.snapshot else fetch_snapshot(args.pr, args.repo)
        errors = audit(snapshot)
        report = {"status": "fail" if errors else "pass", "pr_url": snapshot["pr"]["url"],
                  "checked_issues": len(snapshot["pr"]["closingIssuesReferences"]), "errors": errors}
        exit_code = 1 if errors else 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
        report = {"status": "error", "errors": [f"Could not audit handoff: {detail}"]}
        exit_code = 2
    if args.json:
        print(json.dumps(report, ensure_ascii=True))
    elif exit_code:
        print("\n".join(report["errors"]), file=sys.stderr)
    else:
        print(f"PASS: {report['pr_url']} handoff checked for {report['checked_issues']} linked issues.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
