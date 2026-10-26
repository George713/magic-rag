"""Read-only audit of the issues a pull request will close."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TRIAGE_LABELS = {"needs-triage", "needs-info", "ready-for-agent", "ready-for-human", "wontfix"}
ISSUE_URL = r"https://github\.com/[^/\s]+/[^/\s]+/issues/[1-9][0-9]*"


def section(body, title):
    body = "\n".join(line for _, line in markdown_lines(body))
    heading = re.search(rf"(?im)^##[ \t]+{re.escape(title)}[ \t]*\r?$", body)
    if not heading:
        return ""
    tail = body[heading.end():]
    following = re.search(r"(?m)^#{1,2}[ \t]+", tail)
    return tail[:following.start()] if following else tail


def markdown_lines(body):
    """Inspect active Markdown, excluding fenced examples."""
    fence = None
    for number, line in enumerate(body.splitlines(), 1):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
        elif fence is None:
            yield number, line


def blocker_references(text, issue_url):
    repository_url = issue_url.rsplit("/issues/", 1)[0]
    text = re.sub(rf"\[[^\]]*\]\(({ISSUE_URL})/?\)", r"\1", text)
    return {match.group(0) if match.group(0).startswith("https://") else f"{repository_url}/issues/{match.group(1)}"
            for match in re.finditer(rf"{ISSUE_URL}|(?<![\w/])#([1-9][0-9]*)", text)}


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
        blockers = issue.get("blockedBy")
        if not isinstance(blockers, list):
            raise ValueError(f"{label}: blockedBy must be a complete list of native dependencies.")
        remaining = section(body, "Remaining blockers")
        reasons = {match.group(1).rstrip("/"): match.group(2) for _, line in markdown_lines(remaining)
                   if (match := re.fullmatch(rf"\s*[-*]\s+({ISSUE_URL})/?\s*:\s*(\S.*)", line))}
        blocker_urls = {blocker["url"].rstrip("/") for blocker in blockers}
        if any(not re.fullmatch(ISSUE_URL, url) for url in blocker_urls):
            raise ValueError(f"{label}: native dependencies must use canonical GitHub issue URLs.")
        for _, line in markdown_lines(body):
            entry = re.match(r"^\s*(?:[-*]\s+)?(?:\*\*)?Blocked by:(?:\*\*)?\s*(.+)$", line, re.IGNORECASE)
            if entry:
                blocker_urls.update(blocker_references(entry.group(1), issue["url"]))
        for blocker_url in sorted(blocker_urls):
            if blocker_url not in reasons:
                errors.append(f"{label}: unreconciled blocker {blocker_url}; remove the satisfied relationship or document its unresolved reason in Remaining blockers.")
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
        for line_number, line in markdown_lines(body):
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
    issues = []
    for reference in pr["closingIssuesReferences"]:
        issue = gh_json(["issue", "view", reference["url"], "--json", "number,url,state,labels,body"])
        match = re.fullmatch(r"https://github\.com/([^/]+)/([^/]+)/issues/([1-9][0-9]*)/?", issue["url"])
        if not match:
            raise ValueError(f"Unsupported issue URL: {issue['url']}")
        owner, repository, issue_number = match.groups()
        pages = gh_json(["api", "--paginate", "--slurp",
                         f"repos/{owner}/{repository}/issues/{issue_number}/dependencies/blocked_by?per_page=100"])
        if not isinstance(pages, list) or not pages or any(not isinstance(page, list) for page in pages):
            raise ValueError(f"Issue #{issue_number}: missing native dependency data.")
        issue["blockedBy"] = [{"number": blocker["number"], "url": blocker["html_url"], "state": blocker["state"].upper()}
                              for page in pages for blocker in page]
        issues.append(issue)
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
