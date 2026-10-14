#!/usr/bin/env python3
"""Generate assets/langs.svg, assets/stats.svg and assets/projects.svg.

Runs in GitHub Actions (see .github/workflows/update-cards.yml). Standard library only.

Local test:
    python scripts/gen_cards.py --demo
    GH_USER=your-name python scripts/gen_cards.py
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape

API = "https://api.github.com"
COLORS = ["#74C0FC", "#B197FC", "#8CE99A", "#FFD43B"]
MONO = "'Courier New', Courier, monospace"
SANS = "Arial, Helvetica, sans-serif"
W, H = 390, 250
EXCLUDE_LANGS = {"CSS", "HTML", "SCSS", "Dockerfile"}  # hidden from the language ranking
PW = 800  # projects card width

DEMO = {
    "langs": {"TypeScript": 450, "C#": 300, "Python": 150, "Shell": 60, "HTML": 40},
    "stars": 12,
    "repos": 8,
    "prs": 5,
    "followers": 3,
    "projects": [
        {"name": "Rookie-Ecommerce", "desc": "Full-stack e-commerce application", "lang": "C#", "stars": 1},
        {"name": "demo-api", "desc": "Sample REST API with JWT auth", "lang": "TypeScript", "stars": 0},
    ],
}


def api_get(path, token=None):
    url = path if path.startswith("http") else API + path
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "profile-cards")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_data(user, token):
    profile = api_get(f"/users/{user}", token)
    repos, page = [], 1
    while True:
        batch = api_get(f"/users/{user}/repos?per_page=100&type=owner&page={page}", token)
        repos += batch
        if len(batch) < 100:
            break
        page += 1
    own = [r for r in repos if not r["fork"]]

    langs = Counter()
    for repo in own:
        try:
            langs.update(api_get(repo["languages_url"], token))
        except urllib.error.HTTPError:
            continue

    top = sorted(own, key=lambda r: (r["stargazers_count"], r["pushed_at"]), reverse=True)[:4]
    projects = [
        {"name": r["name"], "desc": r["description"] or "", "lang": r["language"] or "", "stars": r["stargazers_count"]}
        for r in top
    ]
    prs = api_get(f"/search/issues?q=author:{user}+type:pr&per_page=1", token)["total_count"]
    return {
        "langs": dict(langs),
        "stars": sum(r["stargazers_count"] for r in own),
        "repos": profile["public_repos"],
        "prs": prs,
        "followers": profile["followers"],
        "projects": projects,
    }


def top_languages(langs, n=3):
    langs = {k: v for k, v in langs.items() if k not in EXCLUDE_LANGS}
    total = sum(langs.values()) or 1
    ranked = sorted(langs.items(), key=lambda kv: kv[1], reverse=True)
    rows = [(name, size / total * 100) for name, size in ranked[:n]]
    rest = sum(size for _, size in ranked[n:])
    if rest:
        rows.append(("Other", rest / total * 100))
    return rows


def card(bg, title, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'role="img" aria-label="{escape(title)}">'
        f'<rect x="8" y="8" width="{W - 10}" height="{H - 10}" fill="#000000"/>'
        f'<rect x="2" y="2" width="{W - 10}" height="{H - 10}" fill="{bg}" stroke="#000000" stroke-width="3"/>'
        f'<text x="20" y="32" font-family="{MONO}" font-size="14" font-weight="700" fill="#000000">{escape(title)}</text>'
        f"{body}</svg>"
    )


def render_langs(rows):
    track_w = 344
    scale = max((pct for _, pct in rows), default=1) or 1
    parts = []
    for i, (name, pct) in enumerate(rows):
        y = 52 + i * 46
        fill_w = max(8.0, (track_w - 3) * pct / scale)
        color = COLORS[i % len(COLORS)]
        parts.append(
            f'<text x="20" y="{y + 12}" font-family="{MONO}" font-size="12" font-weight="700" fill="#000000">{escape(name)}</text>'
            f'<text x="{20 + track_w}" y="{y + 12}" text-anchor="end" font-family="{MONO}" font-size="12" font-weight="700" fill="#000000">{pct:.1f}%</text>'
            f'<rect x="20" y="{y + 18}" width="{track_w}" height="18" fill="#FFFFFF" stroke="#000000" stroke-width="3"/>'
            f'<rect x="21.5" y="{y + 19.5}" width="{fill_w:.1f}" height="15" fill="{color}"/>'
            f'<rect x="{21.5 + fill_w - 3:.1f}" y="{y + 19.5}" width="3" height="15" fill="#000000"/>'
        )
    return card("#FF8FAB", "// TOP LANGUAGES", "".join(parts))


def render_stats(data):
    cells = [
        ("STARS", data["stars"]),
        ("REPOS", data["repos"]),
        ("PRS", data["prs"]),
        ("FOLLOWERS", data["followers"]),
    ]
    parts = []
    for i, (label, value) in enumerate(cells):
        cx = 20 + (i % 2) * 180
        cy = 50 + (i // 2) * 96
        parts.append(
            f'<rect x="{cx}" y="{cy}" width="170" height="84" fill="#FFFFFF" stroke="#000000" stroke-width="3"/>'
            f'<text x="{cx + 12}" y="{cy + 24}" font-family="{MONO}" font-size="11" font-weight="700" fill="#000000">{label}</text>'
            f'<text x="{cx + 12}" y="{cy + 64}" font-family="{SANS}" font-size="34" font-weight="700" fill="#000000">{value:,}</text>'
        )
    return card("#8CE99A", "// GITHUB STATS", "".join(parts))


def render_projects(projects):
    projects = projects[:4]
    rows = max(1, (len(projects) + 1) // 2)
    ph = 56 + rows * 112 + 12
    colors = ["#74C0FC", "#FFD43B", "#8CE99A", "#B197FC"]
    parts = [
        f'<rect x="8" y="8" width="{PW - 10}" height="{ph - 10}" fill="#000000"/>',
        f'<rect x="2" y="2" width="{PW - 10}" height="{ph - 10}" fill="#FF8FAB" stroke="#000000" stroke-width="3"/>',
        f'<text x="20" y="32" font-family="{MONO}" font-size="14" font-weight="700" fill="#000000">// PROJECTS</text>',
    ]
    for i, pr in enumerate(projects):
        cx = 20 + (i % 2) * 384
        cy = 48 + (i // 2) * 112
        desc = pr["desc"][:48] + ("…" if len(pr["desc"]) > 48 else "")
        meta = " · ".join(x for x in [pr["lang"], f'★ {pr["stars"]}'] if x)
        parts.append(
            f'<rect x="{cx + 5}" y="{cy + 5}" width="368" height="98" fill="#000000"/>'
            f'<rect x="{cx}" y="{cy}" width="368" height="98" fill="{colors[i % 4]}" stroke="#000000" stroke-width="3"/>'
            f'<text x="{cx + 14}" y="{cy + 30}" font-family="{SANS}" font-size="20" font-weight="700" fill="#000000">{escape(pr["name"][:26])}</text>'
            f'<text x="{cx + 14}" y="{cy + 56}" font-family="{SANS}" font-size="13" fill="#000000">{escape(desc)}</text>'
            f'<text x="{cx + 14}" y="{cy + 82}" font-family="{MONO}" font-size="12" font-weight="700" fill="#000000">{escape(meta)}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{PW}" height="{ph}" viewBox="0 0 {PW} {ph}" '
        f'role="img" aria-label="Projects">{"".join(parts)}</svg>'
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--user", default=os.environ.get("GH_USER"))
    parser.add_argument("--out", default="assets")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    if args.demo:
        data = DEMO
    else:
        if not args.user:
            sys.exit("Missing username: use --user or the GH_USER env var")
        data = fetch_data(args.user, os.environ.get("GITHUB_TOKEN"))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "langs.svg").write_text(render_langs(top_languages(data["langs"])), encoding="utf-8")
    (out / "stats.svg").write_text(render_stats(data), encoding="utf-8")
    (out / "projects.svg").write_text(render_projects(data["projects"]), encoding="utf-8")
    print(f"Wrote cards to {out}/")


if __name__ == "__main__":
    main()
