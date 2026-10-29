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
from datetime import UTC, date, datetime, timedelta

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
    """Sort order: rhel by version desc, centos-stream by version desc,
    fedora-rawhide, then fedora by version desc, then arch."""
    parts = name.rsplit("-", 1)
    arch = parts[1] if len(parts) > 1 else ""
    prefix = parts[0]

    if prefix.startswith("rhel-"):
        segments = prefix.rsplit("-", 1)
        try:
            version = -int(segments[1])
        except (ValueError, IndexError):
            version = 0
        return (0, version, arch)
    elif prefix.startswith("centos-stream-"):
        segments = prefix.rsplit("-", 1)
        try:
            version = -int(segments[1])
        except (ValueError, IndexError):
            version = 0
        return (1, version, arch)
    elif prefix.startswith("fedora-rawhide"):
        return (2, 0, arch)
    elif prefix.startswith("fedora-"):
        segments = prefix.rsplit("-", 1)
        try:
            version = -int(segments[1])
        except (ValueError, IndexError):
            version = 0
        return (3, version, arch)
    else:
        return (4, 0, arch)


def parse_chroot(name: str) -> tuple[str, str, str]:
    """Returns (group, version, arch) for a chroot name."""
    parts = name.rsplit("-", 1)
    arch = parts[1] if len(parts) > 1 else name
    prefix = parts[0]

    if prefix.startswith("fedora-rawhide"):
        return ("fedora", "rawhide", arch)
    elif prefix.startswith("fedora-"):
        return ("fedora", prefix.split("-")[1], arch)
    elif prefix.startswith("rhel-"):
        return ("rhel", prefix.split("-")[1], arch)
    elif prefix.startswith("centos-stream-"):
        return ("centos-stream", prefix.split("-")[2], arch)
    return ("other", "", arch)


def chroot_group(name: str) -> str:
    return parse_chroot(name)[0]


GROUP_LABELS = {
    "fedora": "Fedora",
    "rhel": "RHEL",
    "centos-stream": "CentOS Stream",
    "other": "Other",
}


def render_html(rows: list[dict], output_path: str) -> None:
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
    margin: 0;
    background: #fff;
    color: #1f2328;
}
h1 { font-family: "Red Hat Display", sans-serif; font-size: 1.5rem; text-align: center; }
table {
    border-collapse: collapse;
    font-size: 0.75rem;
    width: 100%;
}
th, td {
    border: none;
    padding: 2px 4px;
    text-align: center;
    white-space: nowrap;
}
.group-start { border-left: 2px solid #888; }
th {
    background: #f6f8fa;
}
td.num-col {
    font-weight: bold;
}
th.rotated {
    writing-mode: vertical-rl;
    text-orientation: mixed;
    transform: rotate(180deg);
    max-width: 1.5rem;
    height: 10rem;
    text-align: left;
    font-weight: normal;
    font-size: 0.7rem;
}
a.state-link {
    text-decoration: none;
    font-weight: bold;
    font-size: 0.85rem;
}
a.state-link:hover { text-decoration: underline; }
a.date-link { color: #0969da; }
a.issue-link { color: #0969da; text-decoration: none; }
a.issue-link:hover { text-decoration: underline; }
td.no-build { color: #8b949e; }
tbody tr:nth-child(even) { background: #f6f8fa; }
tbody tr.all-succeeded { background: #dafbe1; }
tbody tr.all-succeeded:nth-child(even) { background: #c7f5d0; }
.streak-row th { font-size: 0.75rem; font-weight: bold; }
a.streak-link { color: inherit; text-decoration: none; }
a.streak-link:hover { text-decoration: underline; }
a.diff-icon { color: #0969da; text-decoration: none; }
a.diff-icon:hover { color: #0550ae; }
.group-header th {
    font-size: 0.75rem;
    font-weight: bold;
}
.version-header th {
    font-size: 0.7rem;
    font-weight: bold;
}
/* Fedora blue (#3c6eb4) */
.group-header .grp-fedora { background: #3c6eb4; color: #fff; }
.version-header .col-fedora { background: #cedbec; }
th.col-fedora { background: #e2eaf3; }
td.col-fedora { background: #cedbec; }
tbody tr:nth-child(even) td.col-fedora { background: #c8d6e9; }
tbody tr.all-succeeded td.col-fedora { background: #dafbe1; }
tbody tr.all-succeeded:nth-child(even) td.col-fedora { background: #c7f5d0; }
/* Red Hat red (#ee0000) */
.group-header .grp-rhel { background: #cc0000; color: #fff; }
.version-header .col-rhel { background: #fcd1d1; }
th.col-rhel { background: #feebeb; }
td.col-rhel { background: #fccccc; }
tbody tr:nth-child(even) td.col-rhel { background: #f4c6c8; }
tbody tr.all-succeeded td.col-rhel { background: #dafbe1; }
tbody tr.all-succeeded:nth-child(even) td.col-rhel { background: #c7f5d0; }
/* CentOS Stream purple (#9c2fa0) */
.group-header .grp-centos-stream { background: #9c2fa0; color: #fff; }
.version-header .col-centos-stream { background: #eddaee; }
th.col-centos-stream { background: #f5edf5; }
td.col-centos-stream { background: #ebd5ec; }
tbody tr:nth-child(even) td.col-centos-stream { background: #e4d0e8; }
tbody tr.all-succeeded td.col-centos-stream { background: #dafbe1; }
tbody tr.all-succeeded:nth-child(even) td.col-centos-stream { background: #c7f5d0; }
a.header-link { color: inherit; text-decoration: none; }
a.header-link:hover { text-decoration: underline; }
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
    last_updated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    html.append("<h1>LLVM Snapshot Builds Dashboard</h1>")
    html.append(f'<p style="margin-top:-0.8rem;font-size:0.85rem;color:#666;text-align:center">(Last updated: {last_updated})</p>')

    html.append('<div class="legend">')
    for state in STATE_SYMBOLS:
        symbol = STATE_SYMBOLS[state]
        html.append(
            f'<span class="legend-item">'
            f'<span class="legend-swatch">{symbol}</span>'
            f"{state}</span>"
        )
    html.append("</div>")

    html.append('<div>')
    html.append("<table>")

    # Compute broken streak and last OK date per chroot
    broken_days: dict[str, int] = {}
    last_ok_date: dict[str, str] = {}
    for chroot in chroots:
        streak = 0
        for d in dates:
            info = data[d].get(chroot)
            if info and info["state"] in ("succeeded", "forked"):
                last_ok_date[chroot] = d
                break
            if info and info["state"] not in ("succeeded", "forked"):
                streak += 1
        broken_days[chroot] = streak

    num_meta_cols = 7  # #, Date, Tracking issue, Maintainer, LLVM Version, commit, changes yesterday

    # Build ordered list of groups and sub-groups (versions)
    groups: list[tuple[str, int]] = []
    versions: list[tuple[str, str, int]] = []  # (group, version, count)
    for chroot in chroots:
        grp, ver, _arch = parse_chroot(chroot)
        if groups and groups[-1][0] == grp:
            groups[-1] = (grp, groups[-1][1] + 1)
        else:
            groups.append((grp, 1))
        if versions and versions[-1][0] == grp and versions[-1][1] == ver:
            versions[-1] = (grp, ver, versions[-1][2] + 1)
        else:
            versions.append((grp, ver, 1))

    # Determine first chroot index of each group for border separators
    group_start_chroots: set[str] = set()
    group_chroots: dict[str, list[str]] = {}
    version_chroots: dict[tuple[str, str], list[str]] = {}
    prev_grp = None
    for chroot in chroots:
        grp, ver, _arch = parse_chroot(chroot)
        if grp != prev_grp:
            group_start_chroots.add(chroot)
            prev_grp = grp
        group_chroots.setdefault(grp, []).append(chroot)
        version_chroots.setdefault((grp, ver), []).append(chroot)

    html.append("<thead>")

    # Row 1: distro group header (Fedora / RHEL / CentOS Stream)
    html.append('<tr class="group-header">')
    html.append(f'<th colspan="{num_meta_cols}"></th>')
    first_grp = True
    for grp, count in groups:
        label = GROUP_LABELS.get(grp, grp)
        cls = f"grp-{grp}" + (" group-start" if not first_grp else "")
        chroot_params = "&amp;".join(f"chroot={c}" for c in group_chroots.get(grp, []))
        link = f"build-times-all-states.html?{chroot_params}"
        html.append(f'<th colspan="{count}" class="{cls}"><a class="header-link" href="{link}">{label}</a></th>')
        first_grp = False
    html.append("</tr>")

    # Row 2: version sub-header (rawhide, 45, 44, 8, 10, 9, ...)
    html.append('<tr class="version-header">')
    html.append(f'<th colspan="{num_meta_cols}"></th>')
    prev_grp = None
    for grp, ver, count in versions:
        cls = f"col-{grp}" + (" group-start" if grp != prev_grp and prev_grp is not None else "")
        chroot_params = "&amp;".join(f"chroot={c}" for c in version_chroots.get((grp, ver), []))
        link = f"build-times-all-states.html?{chroot_params}"
        html.append(f'<th colspan="{count}" class="{cls}"><a class="header-link" href="{link}">{ver}</a></th>')
        prev_grp = grp
    html.append("</tr>")

    # Row 3: arch names (rotated)
    html.append("<tr>")
    html.append('<th class="rotated">#</th>')
    for col in ["Date", "Tracking issue", "Maintainer", "LLVM Version", "LLVM upstream commit", "Changes since yesterday"]:
        html.append(f'<th class="rotated">{col}</th>')
    for chroot in chroots:
        grp, _ver, arch = parse_chroot(chroot)
        gs = " group-start" if chroot in group_start_chroots and chroot != chroots[0] else ""
        link = f"build-times-all-states.html?chroot={chroot}"
        html.append(f'<th class="rotated col-{grp}{gs}"><a class="header-link" href="{link}">{arch}</a></th>')
    html.append("</tr>")

    # Streak row
    html.append('<tr class="streak-row">')
    html.append(f'<th colspan="{num_meta_cols}" style="text-align: right; font-size: 0.7rem;">Days broken →</th>')
    for chroot in chroots:
        grp = chroot_group(chroot)
        gs = " group-start" if chroot in group_start_chroots and chroot != chroots[0] else ""
        days = broken_days[chroot]
        ok_date = last_ok_date.get(chroot)
        if days == 0:
            html.append(f'<th class="col-{grp}{gs}"></th>')
        elif ok_date:
            html.append(f'<th class="col-{grp}{gs}"><a href="#row-{ok_date}" class="streak-link">{days}</a></th>')
        else:
            html.append(f'<th class="col-{grp}{gs}">{days}</th>')
    html.append("</tr>")

    # "Changes since last working build" row
    diff_icon = "∆"
    latest_sha = meta.get(dates[0], {}).get("commit_sha", "") if dates else ""
    html.append('<tr class="streak-row">')
    html.append(f'<th colspan="{num_meta_cols}" style="text-align: right; font-size: 0.7rem;">Changes since last OK →</th>')
    for chroot in chroots:
        grp = chroot_group(chroot)
        gs = " group-start" if chroot in group_start_chroots and chroot != chroots[0] else ""
        days = broken_days[chroot]
        ok_d = last_ok_date.get(chroot)
        ok_sha = meta.get(ok_d, {}).get("commit_sha", "") if ok_d else ""
        if days > 0 and latest_sha and ok_sha and latest_sha != ok_sha:
            diff_url = f"https://github.com/llvm/llvm-project/compare/{ok_sha}...{latest_sha}"
            html.append(f'<th class="col-{grp}{gs}"><a href="{diff_url}" class="diff-icon">{diff_icon}</a></th>')
        else:
            html.append(f'<th class="col-{grp}{gs}"></th>')
    html.append("</tr>")

    html.append("</thead>")

    html.append("<tbody>")
    for idx, d in enumerate(dates):
        entry = data[d]
        yyyymmdd = d.replace("-", "")
        monitor_url = COPR_MONITOR_URL_TPL.format(yyyymmdd=yyyymmdd)
        m = meta.get(d, {})
        all_ok = entry and all(
            info["state"] in ("succeeded", "forked") for info in entry.values()
        )
        row_class = " all-succeeded" if all_ok else ""
        html.append(f'<tr id="row-{d}" class="{row_class.strip()}">' if row_class else f'<tr id="row-{d}">')
        html.append(f'<td class="num-col">{idx}</td>')
        html.append(f'<td><a class="date-link" href="{monitor_url}">{d}</a></td>')

        # Tracking issue
        issue_url = m.get("issue_url")
        if issue_url:
            issue_num = issue_url.rstrip("/").split("/")[-1]
            html.append(f'<td><a class="issue-link" href="{issue_url}">#{issue_num}</a></td>')
        else:
            html.append('<td class="no-build">&mdash;</td>')

        # Maintainer
        assignee = m.get("assignee")
        if assignee:
            html.append(f'<td><a class="issue-link" href="https://github.com/{assignee}">{assignee}</a></td>')
        else:
            html.append('<td class="no-build">&mdash;</td>')

        # LLVM Version
        llvm_version = m.get("llvm_version", "")
        if llvm_version:
            display_version = llvm_version.split(".")[0]
            html.append(f"<td>{display_version}</td>")
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
            html.append(f'<td><a class="diff-icon" href="{diff_url}">{diff_icon}</a></td>')
        else:
            html.append('<td class="no-build">&mdash;</td>')

        for chroot in chroots:
            grp = chroot_group(chroot)
            gs = " group-start" if chroot in group_start_chroots and chroot != chroots[0] else ""
            if chroot in entry:
                info = entry[chroot]
                state = info["state"]
                build_id = info["build_id"]
                symbol = STATE_SYMBOLS.get(state, "?")
                build_url = COPR_BUILD_URL_TPL.format(build_id=build_id)
                html.append(
                    f'<td class="col-{grp}{gs}"><a class="state-link" href="{build_url}" '
                    f'title="{chroot}: {state}">{symbol}</a></td>'
                )
            else:
                html.append(f'<td class="no-build col-{grp}{gs}">&mdash;</td>')
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
        default="dashboard.csv",
        help="Path to the CSV data file (read/write)",
    )
    parser.add_argument(
        "--output",
        default="dashboard.html",
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
    render_html(rows, args.output)
    print(f"Dashboard written to {args.output}")


if __name__ == "__main__":
    main()
