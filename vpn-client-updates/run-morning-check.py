#!/usr/bin/env python3
"""Refresh the public README and Pages table from official release sources.

No credentials or AI service are required. Russian change summaries are
retained for the same version; a new version starts with an em dash until its
summary is added.
"""

from datetime import datetime, timezone
from pathlib import Path
from subprocess import run
from urllib.parse import quote
from zoneinfo import ZoneInfo
import html
import json
import re
import sys

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "version-state.json"
README = ROOT.parent / "README.md"
SITE = ROOT.parent / "site" / "index.html"
LOCAL_TZ = ZoneInfo("Europe/Belgrade")
GITHUB_API = "https://api.github.com/repos/{}/releases?per_page=100"
README_START = "<!-- VPN_CLIENT_UPDATES_START -->"
README_END = "<!-- VPN_CLIENT_UPDATES_END -->"
CLIENTS = ("HAPP", "INCY", "Karing", "Shadowrocket")

GITHUB_ROWS = [
    {"key": "happ_android", "client": "HAPP", "platform": "Android, Android TV", "repo": "Happ-proxy/happ-android", "kind": "latest"},
    {"key": "happ_desktop", "client": "HAPP", "platform": "Windows, macOS, Linux", "repo": "Happ-proxy/happ-desktop", "kind": "latest"},
    {"key": "incy_android", "client": "INCY", "platform": "Android, Android TV", "repo": "INCY-DEV/incy-platforms", "kind": "android"},
    {"key": "incy_desktop", "client": "INCY", "platform": "Windows, macOS, Linux", "repo": "INCY-DEV/incy-platforms", "kind": "desktop"},
    {"key": "karing_desktop_android", "client": "Karing", "platform": "Android, HarmonyOS, Windows, macOS, Linux", "repo": "KaringX/karing", "kind": "latest"},
]

APPLE_ROWS = [
    {"key": "happ_apple", "client": "HAPP", "platform": "iPhone, iPad, macOS (App Store)", "id": "6504287215", "country": "fr", "url": "https://apps.apple.com/fr/app/happ-proxy-utility/id6504287215"},
    {"key": "happ_apple_tv", "client": "HAPP", "platform": "Apple TV", "id": "6748297274", "country": "us", "url": "https://apps.apple.com/us/app/happ-proxy-utility-for-tv/id6748297274?platform=tv"},
    {"key": "incy_apple", "client": "INCY", "platform": "iPhone, iPad, macOS (App Store), Apple TV", "id": "6756943388", "country": "us", "url": "https://apps.apple.com/us/app/incy/id6756943388"},
    {"key": "karing_apple", "client": "Karing", "platform": "iPhone, iPad, Apple TV", "id": "6472431552", "country": "us", "url": "https://apps.apple.com/us/app/karing/id6472431552"},
    {"key": "shadowrocket_apple", "client": "Shadowrocket", "platform": "iPhone, iPad, macOS, Apple TV", "id": "932747118", "country": "us", "url": "https://apps.apple.com/us/app/shadowrocket/id932747118?platform=tv"},
]


def to_local_date(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(LOCAL_TZ).strftime("%d.%m.%Y")


def curl_text(url: str) -> str:
    result = run(
        ["curl", "-fsSL", "--retry", "2", "--retry-delay", "2", "--retry-max-time", "60", "--max-time", "30", "-H", "User-Agent: vpn-client-version-check", url],
        capture_output=True,
        text=True,
        timeout=100,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Source fetch failed ({result.returncode}): {url}\n{result.stderr.strip()}")
    return result.stdout


def fetch_json(url: str) -> dict:
    return json.loads(curl_text(url))


def release_sort_key(release: dict) -> datetime:
    value = release.get("published_at") or release.get("created_at")
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def choose_release(releases: list, kind: str) -> dict:
    candidates = [r for r in releases if not r.get("draft") and not r.get("prerelease")]
    if kind == "android":
        candidates = [r for r in candidates if re.fullmatch(r"android-v\d+\.\d+\.\d+", r.get("tag_name", ""), re.I)]
    elif kind == "desktop":
        candidates = [r for r in candidates if re.fullmatch(r"desktop-v\d+\.\d+\.\d+", r.get("tag_name", ""), re.I)]
    if not candidates:
        raise RuntimeError(f"No stable release found for stream: {kind}")
    return max(candidates, key=release_sort_key)


def fetch_github_row(config: dict) -> dict:
    releases = fetch_json(GITHUB_API.format(config["repo"]))
    release = choose_release(releases, config["kind"])
    tag = release["tag_name"]
    if config["kind"] in ("android", "desktop"):
        version = re.sub(r"^(?:android|desktop)-v", "", tag, flags=re.I)
    else:
        version = re.sub(r"^v", "", tag)
    url = f"https://github.com/{config['repo']}/releases/tag/{quote(tag, safe='')}"
    return {
        **config,
        "version": version,
        "date": to_local_date(release.get("published_at") or release["created_at"]),
        "notes_source": (release.get("body") or "").strip(),
        "url": url,
    }


def fetch_apple_row(config: dict) -> dict:
    url = f"https://itunes.apple.com/lookup?id={config['id']}&country={config['country']}"
    result = fetch_json(url)
    records = result.get("results", [])
    if not records:
        raise RuntimeError(f"App Store result missing for {config['key']}")
    record = records[0]
    return {
        **config,
        "version": record["version"],
        "date": to_local_date(record["currentVersionReleaseDate"]),
        "notes_source": (record.get("releaseNotes") or "").strip(),
    }


def cell(value: str) -> str:
    """Keep source text inside one Markdown table cell."""
    return html.escape(" ".join(str(value).split()), quote=False).replace("\\", "\\\\").replace("|", "\\|")


def render_tables(rows: list) -> str:
    lines = []
    for client in CLIENTS:
        client_rows = [row for row in rows if row["client"] == client]
        if not client_rows:
            continue
        lines.extend([
            f"## {client}", "",
            "| Платформа | Версия | Дата релиза | Что изменилось |",
            "|---|---:|---|---|",
        ])
        for row in client_rows:
            lines.append(
                f"| [{cell(row['platform'])}]({row['url']}) | {cell(row['version'])} | "
                f"{cell(row['date'])} | {cell(row.get('notes') or '—')} |"
            )
        lines.append("")
    return "\n".join(lines).strip()


def render_readme(existing: str, rows: list, updated_at: datetime) -> str:
    if existing.count(README_START) != 1 or existing.count(README_END) != 1:
        raise ValueError("README must contain exactly one pair of update markers")
    start = existing.index(README_START)
    end = existing.index(README_END)
    if end < start:
        raise ValueError("README update markers are in the wrong order")
    updated_at = updated_at.astimezone(LOCAL_TZ)
    generated = (
        f"{README_START}\n\n"
        f"Обновлено: {updated_at:%d.%m.%Y, %H:%M %Z}.\n\n"
        f"{render_tables(rows)}\n\n{README_END}"
    )
    return existing[:start] + generated + existing[end + len(README_END):]


def render_site(rows: list, updated_at: datetime) -> str:
    sections = []
    for client in CLIENTS:
        client_rows = [row for row in rows if row["client"] == client]
        if not client_rows:
            continue
        table_rows = []
        for row in client_rows:
            table_rows.append(
                "<tr>"
                f"<td><a href=\"{html.escape(row['url'], quote=True)}\" target=\"_blank\" rel=\"noopener noreferrer\">{html.escape(row['platform'])}</a></td>"
                f"<td>{html.escape(row['version'])}</td>"
                f"<td>{html.escape(row['date'])}</td>"
                f"<td>{html.escape(row.get('notes') or '—')}</td>"
                "</tr>"
            )
        sections.append(
            f"<details class=\"client\"><summary>{html.escape(client)}</summary>"
            "<div class=\"table-wrap\"><table><thead><tr>"
            "<th>Платформа</th><th>Версия</th><th>Дата релиза</th><th>Что изменилось</th>"
            "</tr></thead><tbody>"
            + "".join(table_rows)
            + "</tbody></table></div></details>"
        )
    local_time = updated_at.astimezone(LOCAL_TZ).strftime("%d.%m.%Y, %H:%M %Z")
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>Актуальные стабильные версии VPN-клиентов</title>
  <style>
    :root {{ color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #202124; background: #fff; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; padding: 24px; }}
    main {{ max-width: 1440px; margin: 0 auto; }}
    h1 {{ margin: 0 0 8px; font-size: clamp(24px, 3vw, 34px); line-height: 1.2; }}
    .updated {{ margin: 0 0 28px; color: #656b73; font-size: 14px; }}
    .client {{ margin: 0 0 10px; border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden; }}
    summary {{ padding: 13px 15px; cursor: pointer; font-size: 16px; font-weight: 600; }}
    details[open] summary {{ border-bottom: 1px solid #e5e7eb; background: #f7f8fa; }}
    .table-wrap {{ overflow-x: auto; border: 1px solid #e5e7eb; border-radius: 10px; }}
    details .table-wrap {{ border: 0; border-radius: 0; }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    th, td {{ padding: 11px 13px; border-bottom: 1px solid #e5e7eb; text-align: left; vertical-align: top; font-size: 14px; line-height: 1.45; overflow-wrap: anywhere; }}
    th {{ background: #f7f8fa; font-weight: 600; }}
    tr:last-child td {{ border-bottom: 0; }}
    th:nth-child(1) {{ width: 24%; }} th:nth-child(2) {{ width: 13%; }} th:nth-child(3) {{ width: 15%; }} th:nth-child(4) {{ width: 48%; }}
    a {{ color: #2457a7; text-decoration: none; }} a:hover {{ text-decoration: underline; }}
    @media (max-width: 680px) {{ body {{ padding: 14px; }} table {{ min-width: 720px; }} }}
  </style>
</head>
<body>
  <main>
    <h1>Актуальные стабильные версии VPN-клиентов</h1>
    <p class="updated">Обновлено: {html.escape(local_time)} · Нажми на приложение, чтобы открыть версии</p>
    {''.join(sections)}
  </main>
</body>
</html>
"""


def state_data(rows: list) -> dict:
    return {
        row["key"]: {
            field: row[field]
            for field in ("client", "platform", "version", "date", "notes", "url")
        }
        for row in rows
    }


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)


def main() -> int:
    try:
        previous = json.loads(STATE.read_text(encoding="utf-8"))
        rows = [fetch_github_row(config) for config in GITHUB_ROWS]
        rows.extend(fetch_apple_row(config) for config in APPLE_ROWS)
        changed = []
        for row in rows:
            old = previous.get(row["key"], {})
            if old.get("version") == row["version"]:
                row["notes"] = old.get("notes") or "—"
            else:
                row["notes"] = "—"
                changed.append(row)
        # A failed source or invalid README aborts before publishing any files.
        readme = render_readme(README.read_text(encoding="utf-8"), rows, datetime.now(LOCAL_TZ))
        state = json.dumps(state_data(rows), ensure_ascii=False, indent=2) + "\n"
        now = datetime.now(LOCAL_TZ)
        site = render_site(rows, now)
        write_atomic(README, readme)
        write_atomic(STATE, state)
        write_atomic(SITE, site)
        if changed:
            summary = "; ".join(f"{r['client']} / {r['platform']}: {r['version']}" for r in changed)
            print(f"RESULT=UPDATES\nUPDATES: {summary}")
        else:
            print("RESULT=NO_UPDATES")
        return 0
    except Exception as exc:
        print(f"CHECK_ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
