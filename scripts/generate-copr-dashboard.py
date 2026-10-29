#!/usr/bin/env python3

"""
Generates an HTML dashboard of LLVM snapshot builds from Copr.

Queries the Copr API for llvm-snapshots-big-merge-YYYYMMDD projects,
stores results in a CSV data file, and renders an HTML table.

Standalone script — no dependencies on the snapshot_manager package.
"""

import argparse
import csv
import json
import os
import re
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import date, timedelta

COPR_API = "https://copr.fedorainfracloud.org/api_3/monitor"
COPR_OWNERNAME = "@fedora-llvm-team"
COPR_PROJECT_TPL = "llvm-snapshots-big-merge-{yyyymmdd}"
COPR_MONITOR_URL_TPL = "https://copr.fedorainfracloud.org/coprs/g/fedora-llvm-team/llvm-snapshots-big-merge-{yyyymmdd}/monitor/"
COPR_BUILD_URL_TPL = "https://copr.fedorainfracloud.org/coprs/build/{build_id}"

GITHUB_REPO = "fedora-llvm-team/llvm-snapshots"
GITHUB_SEARCH_API = "https://api.github.com/search/issues"

CSV_FIELDS = ["date", "chroot", "state", "build_id", "issue_url", "assignee", "llvm_version", "commit_sha"]

STATE_COLORS = {
    "succeeded": "#1a7f37",
    "forked": "#2da44e",
    "failed": "#cf222e",
    "running": "#9a6700",
    "pending": "#666",
    "starting": "#666",
    "importing": "#666",
    "waiting": "#666",
    "canceled": "#888",
    "skipped": "#888",
}

STATE_SYMBOLS = {
    "succeeded": "✅",
    "forked": "☑️",
    "failed": "❌",
    "running": "🏃",
    "pending": "🔜",
    "starting": "⭐",
    "importing": "📥",
    "waiting": "⌛",
    "canceled": "⭕",
    "skipped": "🚫",
}


def fetch_with_retry(url: str, headers: dict | None = None, max_retries: int = 3) -> bytes | None:
    """Fetch a URL with retries on transient errors. Returns None on 404."""
    req = urllib.request.Request(url)
    for k, v in (headers or {}).items():
        req.add_header(k, v)

    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 403:
                wait = 60 * (attempt + 1)
                print(f"rate limited, waiting {wait}s...", end=" ", flush=True)
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, OSError):
            wait = 10 * (attempt + 1)
            print(f"network error, retrying in {wait}s...", end=" ", flush=True)
            time.sleep(wait)
    return None


def fetch_monitor(yyyymmdd: str) -> dict | None:
    projectname = COPR_PROJECT_TPL.format(yyyymmdd=yyyymmdd)
    url = f"{COPR_API}?ownername={COPR_OWNERNAME}&projectname={projectname}"
    data = fetch_with_retry(url)
    if data is None:
        return None
    return json.loads(data)


TITLE_RE = re.compile(r"Snapshot for \d+, v([\d.]+), ([0-9a-f]+)")


def fetch_github_issue(yyyymmdd: str, github_token: str | None = None) -> dict:
    """Returns {issue_url, assignee, llvm_version, commit_sha} or empty strings."""
    result = {"issue_url": "", "assignee": "", "llvm_version": "", "commit_sha": ""}

    query = f'is:issue repo:{GITHUB_REPO} "Snapshot for {yyyymmdd}" in:title label:strategy/big-merge'
    params = urllib.parse.urlencode({"q": query, "per_page": "1"})
    url = f"{GITHUB_SEARCH_API}?{params}"

    headers = {"Accept": "application/vnd.github+json"}
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    raw = fetch_with_retry(url, headers=headers)
    if raw is None:
        return result

    data = json.loads(raw)
    if data.get("total_count", 0) > 0:
        item = data["items"][0]
        result["issue_url"] = item["html_url"]
        assignee = item.get("assignee") or {}
        result["assignee"] = assignee.get("login", "")
        m = TITLE_RE.search(item.get("title", ""))
        if m:
            result["llvm_version"] = m.group(1)
            result["commit_sha"] = m.group(2)
    return result


def extract_chroots(monitor_data: dict) -> dict[str, dict]:
    for pkg in monitor_data.get("packages", []):
        if pkg["name"] == "llvm":
            return {
                chroot: {
                    "state": info["state"],
                    "build_id": info["build_id"],
                }
                for chroot, info in pkg["chroots"].items()
            }
    return {}


def load_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            for field in CSV_FIELDS:
                if field not in row:
                    row[field] = ""
            rows.append(row)
        return rows


def save_csv(path: str, rows: list[dict]) -> None:
    rows.sort(key=lambda r: (r["date"], r["chroot"]))
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def chroot_sort_key(name: str) -> tuple:
    """Sort order: fedora-rawhide first, then fedora by version desc,
    then rhel by version desc, then centos-stream by version desc, then arch."""
    parts = name.rsplit("-", 1)
    arch = parts[1] if len(parts) > 1 else ""
    prefix = parts[0]

    if prefix.startswith("fedora-rawhide"):
        return (0, 0, arch)
    elif prefix.startswith("fedora-"):
        segments = prefix.rsplit("-", 1)
        try:
            version = -int(segments[1])
        except (ValueError, IndexError):
            version = 0
        return (1, version, arch)
    elif prefix.startswith("rhel-"):
        segments = prefix.rsplit("-", 1)
        try:
            version = -int(segments[1])
        except (ValueError, IndexError):
            version = 0
        return (2, version, arch)
    elif prefix.startswith("centos-stream-"):
        segments = prefix.rsplit("-", 1)
        try:
            version = -int(segments[1])
        except (ValueError, IndexError):
            version = 0
        return (3, version, arch)
    else:
        return (4, 0, arch)


def fetch_issue_states(issue_urls: set[str], github_token: str | None = None) -> dict[str, str]:
    """Fetches the current state (open/closed) for each issue URL via the GitHub API."""
    states: dict[str, str] = {}
    headers = {"Accept": "application/vnd.github+json"}
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    for url in sorted(issue_urls):
        api_url = url.replace("https://github.com/", "https://api.github.com/repos/").replace("/issues/", "/issues/")
        raw = fetch_with_retry(api_url, headers=headers)
        if raw is None:
            continue
        data = json.loads(raw)
        states[url] = data.get("state", "")
    return states


def render_html(rows: list[dict], output_path: str, github_token: str | None = None) -> None:
    data: dict[str, dict[str, dict]] = {}
    meta: dict[str, dict] = {}
    all_chroots: set[str] = set()

    for row in rows:
        d = row["date"]
        chroot = row["chroot"]
        if d not in data:
            data[d] = {}
            meta[d] = {}
        data[d][chroot] = {"state": row["state"], "build_id": row["build_id"]}
        all_chroots.add(chroot)
        if row.get("issue_url"):
            meta[d]["issue_url"] = row["issue_url"]
        if row.get("assignee"):
            meta[d]["assignee"] = row["assignee"]
        if row.get("llvm_version"):
            meta[d]["llvm_version"] = row["llvm_version"]
        if row.get("commit_sha"):
            meta[d]["commit_sha"] = row["commit_sha"]

    chroots = sorted(all_chroots, key=chroot_sort_key)
    dates = sorted(data.keys(), reverse=True)

    all_issue_urls = {m.get("issue_url") for m in meta.values() if m.get("issue_url")}
    if github_token:
        print(f"Fetching state for {len(all_issue_urls)} issues...", flush=True)
        issue_states = fetch_issue_states(all_issue_urls, github_token)
    else:
        print("Warning: no GITHUB_TOKEN set, skipping issue state fetch to avoid rate limiting")
        issue_states = {}

    html = []
    html.append("<!DOCTYPE html>")
    html.append('<html lang="en">')
    html.append("<head>")
    html.append('<meta charset="utf-8">')
    html.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    html.append("<title>LLVM Snapshot Builds Dashboard</title>")
    html.append('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Red+Hat+Display:wght@400;700&family=Red+Hat+Text:wght@400;700&family=Red+Hat+Mono&display=swap">')
    html.append("<style>")
    html.append("""
body {
    font-family: "Red Hat Text", -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    margin: 1rem;
    background: #fff;
    color: #1f2328;
}
h1 { font-family: "Red Hat Display", sans-serif; font-size: 1.5rem; text-align: center; }
table {
    border-collapse: collapse;
    font-size: 0.8rem;
    width: 100%;
}
th, td {
    border-top: 1px solid #d1d9e0;
    border-bottom: 1px solid #d1d9e0;
    border-left: none;
    border-right: none;
    padding: 4px 8px;
    text-align: center;
    white-space: nowrap;
}
th {
    background: #f6f8fa;
    z-index: 1;
}
thead th {
    position: sticky;
    top: 0;
}
td.num-col {
    font-weight: bold;
}
th.rotated {
    writing-mode: vertical-rl;
    text-orientation: mixed;
    transform: rotate(180deg);
    max-width: 2rem;
    height: 12rem;
    text-align: left;
    font-weight: normal;
    font-size: 0.75rem;
}
a.state-link {
    text-decoration: none;
    font-weight: bold;
    font-size: 1rem;
}
a.state-link:hover { text-decoration: underline; }
a.date-link { color: #0969da; }
a.issue-link { color: #0969da; text-decoration: none; }
a.issue-link:hover { text-decoration: underline; }
td.no-build { color: #8b949e; }
tbody tr:nth-child(even) { background: #f6f8fa; }
tbody tr.all-succeeded { background: #dafbe1; }
tbody tr.all-succeeded:nth-child(even) { background: #c7f5d0; }
.legend {
    margin-bottom: 1rem;
    font-size: 0.8rem;
    display: flex;
    gap: 1.5rem;
    flex-wrap: wrap;
    justify-content: center;
}
.legend-item { display: flex; align-items: center; gap: 0.3rem; }
.legend-swatch {
    display: inline-block;
    width: 1rem;
    height: 1rem;
    border-radius: 2px;
    text-align: center;
    line-height: 1rem;
    font-size: 0.75rem;
    font-weight: bold;
}
""")
    html.append("</style>")
    html.append("</head>")
    html.append("<body>")
    html.append("<h1>LLVM Snapshot Builds Dashboard</h1>")

    html.append('<div class="legend">')
    for state in STATE_SYMBOLS:
        symbol = STATE_SYMBOLS[state]
        html.append(
            f'<span class="legend-item">'
            f'<span class="legend-swatch">{symbol}</span>'
            f"{state}</span>"
        )
    html.append("</div>")

    html.append('<div style="overflow: auto; max-height: calc(100vh - 10rem);">')
    html.append("<table>")

    html.append("<thead><tr>")
    html.append('<th class="rotated">#</th>')
    for col in ["Date", "Tracking issue", "Assignee", "LLVM Version", "LLVM upstream commit", "Changes since yesterday"]:
        html.append(f'<th class="rotated">{col}</th>')
    for chroot in chroots:
        html.append(f'<th class="rotated">{chroot}</th>')
    html.append("</tr></thead>")

    html.append("<tbody>")
    for idx, d in enumerate(dates):
        entry = data[d]
        yyyymmdd = d.replace("-", "")
        monitor_url = COPR_MONITOR_URL_TPL.format(yyyymmdd=yyyymmdd)
        m = meta.get(d, {})
        all_ok = entry and all(
            info["state"] in ("succeeded", "forked") for info in entry.values()
        )
        row_class = ' class="all-succeeded"' if all_ok else ""
        html.append(f"<tr{row_class}>")
        html.append(f'<td class="num-col">{idx}</td>')
        html.append(f'<td><a class="date-link" href="{monitor_url}">{d}</a></td>')

        # Tracking issue
        issue_url = m.get("issue_url")
        if issue_url:
            issue_num = issue_url.rstrip("/").split("/")[-1]
            issue_state = issue_states.get(issue_url)
            if issue_state == "closed":
                issue_icon = "🟣"
            elif issue_state == "open":
                issue_icon = "🟢"
            else:
                issue_icon = "⚪"
            html.append(f'<td><a class="issue-link" href="{issue_url}">{issue_icon} #{issue_num}</a></td>')
        else:
            html.append('<td class="no-build">&mdash;</td>')

        # Assignee
        assignee = m.get("assignee")
        if assignee:
            html.append(f'<td><a class="issue-link" href="https://github.com/{assignee}">{assignee}</a></td>')
        else:
            html.append('<td class="no-build">&mdash;</td>')

        # LLVM Version
        llvm_version = m.get("llvm_version", "")
        if llvm_version:
            html.append(f"<td>{llvm_version}</td>")
        else:
            html.append('<td class="no-build">&mdash;</td>')

        # Commit
        commit_sha = m.get("commit_sha", "")
        if commit_sha:
            commit_url = f"https://github.com/llvm/llvm-project/commit/{commit_sha}"
            html.append(f'<td><a class="issue-link" href="{commit_url}">{commit_sha}</a></td>')
        else:
            html.append('<td class="no-build">&mdash;</td>')

        # Changes since yesterday
        prev_date = dates[idx + 1] if idx + 1 < len(dates) else None
        prev_sha = meta.get(prev_date, {}).get("commit_sha", "") if prev_date else ""
        if commit_sha and prev_sha and commit_sha != prev_sha:
            diff_url = f"https://github.com/llvm/llvm-project/compare/{prev_sha}...{commit_sha}"
            html.append(f'<td><a class="issue-link" href="{diff_url}">diff</a></td>')
        else:
            html.append('<td class="no-build">&mdash;</td>')

        for chroot in chroots:
            if chroot in entry:
                info = entry[chroot]
                state = info["state"]
                build_id = info["build_id"]
                symbol = STATE_SYMBOLS.get(state, "?")
                build_url = COPR_BUILD_URL_TPL.format(build_id=build_id)
                html.append(
                    f'<td><a class="state-link" href="{build_url}" '
                    f'title="{chroot}: {state}">{symbol}</a></td>'
                )
            else:
                html.append('<td class="no-build">&mdash;</td>')
        html.append("</tr>")
    html.append("</tbody>")

    html.append("</table>")
    html.append("</div>")

    html.append("</body>")
    html.append("</html>")

    with open(output_path, "w") as f:
        f.write("\n".join(html))
        f.write("\n")


def main():
    parser = argparse.ArgumentParser(description="Generate LLVM snapshot builds dashboard")
    parser.add_argument(
        "--data-file",
        default="copr-dashboard.csv",
        help="Path to the CSV data file (read/write)",
    )
    parser.add_argument(
        "--output",
        default="copr-dashboard.html",
        help="Path to the output HTML file",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=90,
        help="How many days to look back for missing data (default: 90)",
    )
    args = parser.parse_args()

    github_token = os.environ.get("GITHUB_TOKEN")

    rows = load_csv(args.data_file)

    existing: dict[str, set[str]] = {}
    for row in rows:
        existing.setdefault(row["date"], set()).add(row["chroot"])

    today = date.today()
    new_entries = 0

    for i in range(args.lookback_days + 1):
        d = today - timedelta(days=i)
        key = d.isoformat()
        yyyymmdd = d.strftime("%Y%m%d")

        if key in existing:
            continue

        print(f"Fetching {yyyymmdd}...", end=" ", flush=True)
        monitor = fetch_monitor(yyyymmdd)
        if monitor is None:
            print("no project")
            continue

        chroots = extract_chroots(monitor)
        if not chroots:
            print("no llvm package")
            continue

        gh = fetch_github_issue(yyyymmdd, github_token)
        known = existing.get(key, set())
        for chroot, info in chroots.items():
            if chroot in known:
                continue
            rows.append({
                "date": key,
                "chroot": chroot,
                "state": info["state"],
                "build_id": info["build_id"],
                "issue_url": gh["issue_url"],
                "assignee": gh["assignee"],
                "llvm_version": gh["llvm_version"],
                "commit_sha": gh["commit_sha"],
            })
        existing.setdefault(key, set()).update(chroots.keys())

        new_entries += 1
        suffix = f", issue: {gh['issue_url']}" if gh["issue_url"] else ""
        print(f"{len(chroots)} chroots{suffix}")

        if new_entries % 5 == 0:
            save_csv(args.data_file, rows)

    print(f"\nTotal dates: {len({r['date'] for r in rows})}, new: {new_entries}")

    save_csv(args.data_file, rows)
    render_html(rows, args.output, github_token)
    print(f"Dashboard written to {args.output}")


if __name__ == "__main__":
    main()
