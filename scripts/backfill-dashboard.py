#!/usr/bin/env python3

"""
Backfills the dashboard CSV from GitHub issues.

Fetches all issues with label strategy/big-merge from the llvm-snapshots
repo, parses the build matrix from the issue body, and writes the same
CSV format used by generate-dashboard.py.

This is a one-time script for seeding historical data.
"""

import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

GITHUB_REPO = "fedora-llvm-team/llvm-snapshots"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/issues"

CSV_FIELDS = ["date", "chroot", "state", "build_id", "issue_url", "assignee", "llvm_version", "commit_sha"]

TITLE_RE = re.compile(r"Snapshot for (\d{8}), v([\d.]+), ([0-9a-f]+) \(big-merge\)")

EMOJI_TO_STATE = {
    "white_check_mark": "succeeded",
    "ballot_box_with_check": "forked",
    "x": "failed",
    "running": "running",
    "soon": "pending",
    "star": "starting",
    "inbox_tray": "importing",
    "hourglass": "waiting",
    "o": "canceled",
    "no_entry_sign": "skipped",
    "grey_question": "unknown",
}

BUILD_ROW_RE = re.compile(
    r"^\|([a-z][a-z0-9_-]+)"
    r"(?:<br\s*/?>.*?)?"
    r"\|\[:([\w]+):\]\(https://copr\.fedorainfracloud\.org/coprs/build/(\d+)\)\|"
)


def fetch_all_issues(github_token: str) -> list[dict]:
    """Fetches all big-merge issues, paginating through the API."""
    all_issues = []
    page = 1
    per_page = 100

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {github_token}",
    }

    while True:
        params = urllib.parse.urlencode({
            "labels": "strategy/big-merge",
            "state": "all",
            "per_page": str(per_page),
            "page": str(page),
            "direction": "desc",
        })
        url = f"{GITHUB_API}?{params}"

        req = urllib.request.Request(url)
        for k, v in headers.items():
            req.add_header(k, v)

        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read())
                    break
            except urllib.error.HTTPError as e:
                if e.code == 403:
                    wait = 60 * (attempt + 1)
                    print(f"  rate limited, waiting {wait}s...", flush=True)
                    time.sleep(wait)
                    continue
                raise
            except (urllib.error.URLError, OSError):
                wait = 10 * (attempt + 1)
                print(f"  network error, retrying in {wait}s...", flush=True)
                time.sleep(wait)
        else:
            print(f"  failed to fetch page {page}, stopping", flush=True)
            break

        if not data:
            break

        all_issues.extend(data)
        print(f"  page {page}: {len(data)} issues (total: {len(all_issues)})", flush=True)

        if len(data) < per_page:
            break
        page += 1

    return all_issues


def parse_title(title: str) -> dict:
    m = TITLE_RE.search(title)
    if not m:
        return {}
    yyyymmdd = m.group(1)
    date_str = f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"
    return {"date": date_str, "llvm_version": m.group(2), "commit_sha": m.group(3)}


def parse_build_matrix(body: str) -> list[dict]:
    """Parses build matrix rows from the issue body."""
    results = []
    for line in body.split("\n"):
        m = BUILD_ROW_RE.match(line)
        if m:
            chroot = m.group(1)
            emoji = m.group(2)
            build_id = m.group(3)
            state = EMOJI_TO_STATE.get(emoji, "unknown")
            results.append({"chroot": chroot, "state": state, "build_id": build_id})
    return results


def main():
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        print("Error: GITHUB_TOKEN environment variable required", file=sys.stderr)
        sys.exit(1)

    output_file = sys.argv[1] if len(sys.argv) > 1 else "dashboard.csv"

    existing_keys: set[tuple[str, str]] = set()
    existing_rows: list[dict] = []
    if os.path.exists(output_file):
        with open(output_file, newline="") as f:
            existing_rows = list(csv.DictReader(f))
            existing_keys = {(row["date"], row["chroot"]) for row in existing_rows}
        existing_dates = {row["date"] for row in existing_rows}
        print(f"Loaded {len(existing_dates)} existing dates, {len(existing_keys)} entries from {output_file}")

    print("Fetching issues from GitHub...", flush=True)
    issues = fetch_all_issues(github_token)
    print(f"Fetched {len(issues)} issues total\n")

    rows = list(existing_rows)
    new_entries = 0
    skipped = 0
    unparseable = 0

    for issue in issues:
        title_info = parse_title(issue["title"])
        if not title_info or not title_info.get("date"):
            unparseable += 1
            continue

        date_str = title_info["date"]

        body = issue.get("body") or ""
        builds = parse_build_matrix(body)
        if not builds:
            print(f"  #{issue['number']} ({date_str}): no build matrix found, skipping")
            unparseable += 1
            continue

        assignee = (issue.get("assignee") or {}).get("login", "")
        issue_url = issue["html_url"]

        added = 0
        for build in builds:
            key = (date_str, build["chroot"])
            if key in existing_keys:
                skipped += 1
                continue
            rows.append({
                "date": date_str,
                "chroot": build["chroot"],
                "state": build["state"],
                "build_id": build["build_id"],
                "issue_url": issue_url,
                "assignee": assignee,
                "llvm_version": title_info.get("llvm_version", ""),
                "commit_sha": title_info.get("commit_sha", ""),
            })
            existing_keys.add(key)
            added += 1

        if added:
            new_entries += added
            print(f"  #{issue['number']} ({date_str}): {added} new chroots, assignee={assignee}")

    rows.sort(key=lambda r: (r["date"], r["chroot"]))

    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    total_dates = len({r["date"] for r in rows})
    print(f"\nDone: {total_dates} total dates, {new_entries} new entries, {skipped} skipped, {unparseable} unparseable")
    print(f"Written to {output_file}")


if __name__ == "__main__":
    main()
