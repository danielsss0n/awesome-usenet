#!/usr/bin/env python3
"""
Syncs newly published datahoarder.io posts into README.md.
Run on a schedule by .github/workflows/sync-blog-posts.yml — no manual steps.
"""
import html
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

SITE = "https://datahoarder.io"
STATE_FILE = Path("last_synced.json")
README = Path("README.md")

# WordPress category ID -> README section marker.
# IDs confirmed against the live site (2026-07-27).
CATEGORY_MAP = {
    1: "usenet",       # Usenet (providers, indexers, newsreaders)
    31: "automation",  # Automation (*arr stack, Docker, etc.)
    32: "nas",         # NAS / storage
    6: "vpn",          # VPN / privacy
}
DEFAULT_SECTION = "general"


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_synced": "2026-01-01T00:00:00"}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def fetch_new_posts(after_iso):
    url = (
        f"{SITE}/wp-json/wp/v2/posts"
        f"?after={after_iso}&status=publish&per_page=100&orderby=date&order=asc"
        f"&_fields=id,date,title,link,categories,excerpt"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "datahoarder-resource-sync/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def strip_html(text):
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\.\.\.\s*$", "", text).strip()
    return re.sub(r"\s+", " ", text)


def section_for(post):
    for cat_id in post.get("categories", []):
        if cat_id in CATEGORY_MAP:
            return CATEGORY_MAP[cat_id]
    return DEFAULT_SECTION


def format_entry(post):
    title = strip_html(post["title"]["rendered"])
    excerpt = strip_html(post["excerpt"]["rendered"])[:140].rstrip()
    if excerpt and not excerpt.endswith((".", "!", "?")):
        excerpt += "..."
    return f"- [{title}]({post['link']}) — {excerpt}"


def insert_entries(readme_text, section, entries):
    start = f"<!-- SYNC:{section}:START -->"
    end = f"<!-- SYNC:{section}:END -->"
    if start not in readme_text:
        # Section doesn't exist yet — append a new one at the end, before any trailing footer.
        block = f"\n## {section.title()}\n{start}\n{end}\n"
        readme_text += block
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    existing = pattern.search(readme_text).group(0)
    inner = existing[len(start):-len(end)].strip("\n")
    new_inner = (inner + "\n" if inner else "") + "\n".join(entries)
    replacement = f"{start}\n{new_inner}\n{end}"
    return pattern.sub(replacement, readme_text)


def main():
    state = load_state()
    posts = fetch_new_posts(state["last_synced"])

    if not posts:
        print("No new posts since", state["last_synced"])
        return

    by_section = {}
    for post in posts:
        by_section.setdefault(section_for(post), []).append(format_entry(post))

    readme_text = README.read_text() if README.exists() else "# Datahoarder.io Resource List\n"
    for section, entries in by_section.items():
        readme_text = insert_entries(readme_text, section, entries)
    README.write_text(readme_text)

    state["last_synced"] = posts[-1]["date"]
    save_state(state)
    print(f"Added {len(posts)} post(s) across {len(by_section)} section(s).")


if __name__ == "__main__":
    sys.exit(main())
