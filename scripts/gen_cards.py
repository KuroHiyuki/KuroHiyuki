#!/usr/bin/env python3
"""Generate assets/langs.svg, assets/stats.svg and assets/projects.svg.

Runs in GitHub Actions (see .github/workflows/update-cards.yml). Standard library only.

Local test:
    python scripts/gen_cards.py --demo
    GH_USER=your-name python scripts/gen_cards.py
"""
import argparse
import base64
import datetime
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
PW = 800  # full-width card width
NAME = "Nguyễn Phương"
INITIALS = "NP"
ROLE = "SOFTWARE ENGINEER"
TAGLINE = "Turning coffee into code that scales."
LEVEL_COLORS = {
    "NONE": "#FFFFFF",
    "FIRST_QUARTILE": "#B2F2BB",
    "SECOND_QUARTILE": "#8CE99A",
    "THIRD_QUARTILE": "#40C057",
    "FOURTH_QUARTILE": "#000000",
}

DEMO = {
    "langs": {"TypeScript": 450, "C#": 300, "Python": 150, "Shell": 60, "HTML": 40},
    "stars": 12,
    "repos": 8,
    "prs": 5,
    "followers": 3,
    "avatar": None,
    "calendar": {"total": 97, "weeks": [
        [{"date": "2026-01-%02d" % (1 + (w * 7 + d) % 28), "level": ["NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE"][(w * 3 + d * 5) % 5 if (w + d) % 3 == 0 else 0]} for d in range(7)]
        for w in range(53)
    ]},
    "month": {
        "label": "October 2026",
        "commits": 74,
        "commit_repos": [("demo/app", 62), ("demo/demo", 12)],
        "created_repos": [("demo/demo", "Python", "Oct 14")],
        "prs": 2,
        "issues": 1,
    },
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
    shown = [r for r in own if r["name"].lower() != user.lower()]  # hide the profile repo itself

    langs = Counter()
    for repo in own:
        try:
            langs.update(api_get(repo["languages_url"], token))
        except urllib.error.HTTPError:
            continue

    top = sorted(shown, key=lambda r: (r["stargazers_count"], r["pushed_at"]), reverse=True)[:4]
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
        "avatar": fetch_avatar(user, token),
        **fetch_activity(user, token),
    }


def graphql(query, variables, token):
    req = urllib.request.Request(
        API + "/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        method="POST",
    )
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("User-Agent", "profile-cards")
    with urllib.request.urlopen(req, timeout=30) as resp:
        out = json.load(resp)
    if out.get("errors"):
        raise RuntimeError(out["errors"])
    return out["data"]


GQL = """
query($login: String!, $from: DateTime!) {
  user(login: $login) {
    year: contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionLevel } }
      }
    }
    month: contributionsCollection(from: $from) {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      commitContributionsByRepository(maxRepositories: 5) {
        repository { nameWithOwner }
        contributions { totalCount }
      }
      repositoryContributions(first: 4) {
        nodes { occurredAt repository { nameWithOwner primaryLanguage { name } } }
      }
    }
  }
}
"""


def fetch_activity(user, token):
    """Contribution graph + this month's activity. Needs a token; returns {} on failure."""
    if not token:
        return {}
    now = datetime.datetime.now(datetime.timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    try:
        u = graphql(GQL, {"login": user, "from": start.strftime("%Y-%m-%dT%H:%M:%SZ")}, token)["user"]
    except Exception as exc:  # keep the other cards working
        print("GraphQL failed:", exc, file=sys.stderr)
        return {}
    cal = u["year"]["contributionCalendar"]
    m = u["month"]
    return {
        "calendar": {
            "total": cal["totalContributions"],
            "weeks": [
                [{"date": d["date"], "level": d["contributionLevel"]} for d in w["contributionDays"]]
                for w in cal["weeks"]
            ],
        },
        "month": {
            "label": now.strftime("%B %Y"),
            "commits": m["totalCommitContributions"],
            "commit_repos": [
                (c["repository"]["nameWithOwner"], c["contributions"]["totalCount"])
                for c in m["commitContributionsByRepository"]
            ],
            "created_repos": [
                (
                    n["repository"]["nameWithOwner"],
                    (n["repository"]["primaryLanguage"] or {}).get("name", ""),
                    n["occurredAt"][:10],
                )
                for n in m["repositoryContributions"]["nodes"]
            ],
            "prs": m["totalPullRequestContributions"],
            "issues": m["totalIssueContributions"],
        },
    }


def fetch_avatar(user, token):
    """Download the GitHub avatar as a data URI (SVG-as-image cannot load external images)."""
    try:
        req = urllib.request.Request(f"https://github.com/{user}.png?size=300")
        req.add_header("User-Agent", "profile-cards")
        with urllib.request.urlopen(req, timeout=30) as resp:
            mime = resp.headers.get_content_type()
            data = resp.read()
        return f"data:{mime};base64," + base64.b64encode(data).decode()
    except Exception as exc:
        print("Avatar download failed:", exc, file=sys.stderr)
        return None


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
    card_w = 752 if len(projects) == 1 else 368
    for i, pr in enumerate(projects):
        cx = 20 + (i % 2) * 384
        cy = 48 + (i // 2) * 112
        desc = pr["desc"][:48] + ("…" if len(pr["desc"]) > 48 else "")
        meta = " · ".join(x for x in [pr["lang"], f'★ {pr["stars"]}'] if x)
        parts.append(
            f'<rect x="{cx + 5}" y="{cy + 5}" width="{card_w}" height="98" fill="#000000"/>'
            f'<rect x="{cx}" y="{cy}" width="{card_w}" height="98" fill="{colors[i % 4]}" stroke="#000000" stroke-width="3"/>'
            f'<text x="{cx + 14}" y="{cy + 30}" font-family="{SANS}" font-size="20" font-weight="700" fill="#000000">{escape(pr["name"][:26])}</text>'
            f'<text x="{cx + 14}" y="{cy + 56}" font-family="{SANS}" font-size="13" fill="#000000">{escape(desc)}</text>'
            f'<text x="{cx + 14}" y="{cy + 82}" font-family="{MONO}" font-size="12" font-weight="700" fill="#000000">{escape(meta)}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{PW}" height="{ph}" viewBox="0 0 {PW} {ph}" '
        f'role="img" aria-label="Projects">{"".join(parts)}</svg>'
    )


def render_header(avatar):
    if avatar:
        face = (
            f'<image x="600" y="56" width="150" height="150" preserveAspectRatio="xMidYMid slice" href="{avatar}"/>'
            '<rect x="600" y="56" width="150" height="150" fill="none" stroke="#000000" stroke-width="3"/>'
        )
    else:
        face = (
            '<rect x="600" y="56" width="150" height="150" fill="#74C0FC" stroke="#000000" stroke-width="3"/>'
            f'<text x="675" y="150" text-anchor="middle" font-family="{SANS}" font-size="64" font-weight="700" '
            f'letter-spacing="-3" fill="#000000">{escape(INITIALS)}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="800" height="260" '
        f'viewBox="0 0 800 260" role="img" aria-label="{escape(NAME)}, {escape(ROLE.title())}">'
        '<rect width="800" height="260" fill="#FFD43B"/>'
        '<rect x="2" y="2" width="796" height="256" fill="none" stroke="#000000" stroke-width="4"/>'
        '<rect x="42" y="42" width="520" height="190" fill="#000000"/>'
        '<rect x="34" y="34" width="520" height="190" fill="#FFFFFF" stroke="#000000" stroke-width="3"/>'
        '<g transform="rotate(-3 113 62)">'
        '<rect x="48" y="48" width="130" height="28" fill="#FF8FAB" stroke="#000000" stroke-width="3"/>'
        f'<text x="113" y="67" text-anchor="middle" font-family="{MONO}" font-size="14" font-weight="700" fill="#000000">HELLO, I\'M</text>'
        "</g>"
        f'<text x="48" y="128" font-family="{SANS}" font-size="50" font-weight="700" letter-spacing="-2" fill="#000000">{escape(NAME)}</text>'
        '<rect x="48" y="144" width="190" height="30" fill="#000000"/>'
        f'<text x="60" y="165" font-family="{MONO}" font-size="16" font-weight="700" fill="#FFD43B">{escape(ROLE)}</text>'
        f'<text x="48" y="204" font-family="{SANS}" font-size="15" fill="#000000">{escape(TAGLINE)}</text>'
        '<g transform="rotate(3 675 131)">'
        '<rect x="608" y="64" width="150" height="150" fill="#000000"/>'
        f"{face}</g></svg>"
    )


def full_card(height, bg, title, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{PW}" height="{height}" viewBox="0 0 {PW} {height}" '
        f'role="img" aria-label="{escape(title)}">'
        f'<rect x="8" y="8" width="{PW - 10}" height="{height - 10}" fill="#000000"/>'
        f'<rect x="2" y="2" width="{PW - 10}" height="{height - 10}" fill="{bg}" stroke="#000000" stroke-width="3"/>'
        f'<text x="20" y="32" font-family="{MONO}" font-size="14" font-weight="700" fill="#000000">{escape(title)}</text>'
        f"{body}</svg>"
    )


def render_contrib(cal):
    weeks = cal["weeks"]
    cell, x0, y0 = 11, 48, 62
    step = 13.5
    parts = []
    last_month = None
    for wi, week in enumerate(weeks):
        x = round(x0 + wi * step, 1)
        month = week[0]["date"][5:7] if week else None
        if month != last_month and wi < len(weeks) - 2:
            name = datetime.date(2000, int(month), 1).strftime("%b").upper()
            parts.append(
                f'<text x="{x}" y="{y0 - 8}" font-family="{MONO}" font-size="10" font-weight="700" fill="#000000">{name}</text>'
            )
            last_month = month
        for di, day in enumerate(week):
            color = LEVEL_COLORS.get(day["level"], "#FFFFFF")
            parts.append(
                f'<rect x="{x}" y="{round(y0 + di * step, 1)}" width="{cell}" height="{cell}" fill="{color}" '
                'stroke="#000000" stroke-width="1.5"/>'
            )
    for label, di in (("MON", 1), ("WED", 3), ("FRI", 5)):
        parts.append(
            f'<text x="20" y="{round(y0 + di * step + 9, 1)}" font-family="{MONO}" font-size="10" font-weight="700" fill="#000000">{label}</text>'
        )
    ly = int(y0 + 7 * step + 10)
    parts.append(f'<text x="540" y="{ly + 9}" font-family="{MONO}" font-size="10" font-weight="700" fill="#000000">LESS</text>')
    for i, key in enumerate(LEVEL_COLORS):
        parts.append(
            f'<rect x="{574 + i * 16}" y="{ly}" width="11" height="11" fill="{LEVEL_COLORS[key]}" stroke="#000000" stroke-width="1.5"/>'
        )
    parts.append(f'<text x="660" y="{ly + 9}" font-family="{MONO}" font-size="10" font-weight="700" fill="#000000">MORE</text>')
    title = f"// {cal['total']:,} CONTRIBUTIONS IN THE LAST YEAR"
    return full_card(ly + 28, "#FFD43B", title, "".join(parts))


def render_activity(m):
    parts = []
    y = 56
    bar_x, bar_w = 400, 360
    top = max([n for _, n in m["commit_repos"]] or [1]) or 1

    def pill(text, color, y):
        w = 8 * len(text) + 20
        return (
            f'<rect x="25" y="{y + 5}" width="{w}" height="26" fill="#000000"/>'
            f'<rect x="20" y="{y}" width="{w}" height="26" fill="{color}" stroke="#000000" stroke-width="3"/>'
            f'<text x="30" y="{y + 18}" font-family="{MONO}" font-size="12" font-weight="700" fill="#000000">{escape(text)}</text>'
        )

    plural = "repository" if len(m["commit_repos"]) == 1 else "repositories"
    parts.append(pill(f"CREATED {m['commits']:,} COMMITS IN {len(m['commit_repos'])} {plural.upper()}", "#FF8FAB", y))
    y += 48
    for name, n in m["commit_repos"]:
        w = max(8.0, (bar_w - 3) * n / top)
        parts.append(
            f'<text x="24" y="{y + 12}" font-family="{SANS}" font-size="14" font-weight="700" fill="#000000">{escape(name[:34])}</text>'
            f'<text x="{bar_x - 12}" y="{y + 12}" text-anchor="end" font-family="{MONO}" font-size="12" font-weight="700" fill="#000000">{n} COMMITS</text>'
            f'<rect x="{bar_x}" y="{y}" width="{bar_w}" height="16" fill="#FFFFFF" stroke="#000000" stroke-width="3"/>'
            f'<rect x="{bar_x + 1.5}" y="{y + 1.5}" width="{w:.1f}" height="13" fill="#8CE99A"/>'
            f'<rect x="{bar_x + 1.5 + w - 3:.1f}" y="{y + 1.5}" width="3" height="13" fill="#000000"/>'
        )
        y += 30
    if m["created_repos"]:
        y += 10
        n_new = len(m["created_repos"])
        parts.append(pill(f"CREATED {n_new} {'REPOSITORY' if n_new == 1 else 'REPOSITORIES'}", "#B197FC", y))
        y += 46
        for name, lang, date in m["created_repos"]:
            meta = " | ".join(x for x in [lang, date] if x)
            parts.append(
                f'<text x="24" y="{y + 12}" font-family="{SANS}" font-size="14" font-weight="700" fill="#000000">{escape(name[:34])}</text>'
                f'<text x="{bar_x + bar_w}" y="{y + 12}" text-anchor="end" font-family="{MONO}" font-size="12" font-weight="700" fill="#000000">{escape(meta)}</text>'
            )
            y += 26
    extra = []
    if m["prs"]:
        extra.append(f"{m['prs']} PULL REQUESTS")
    if m["issues"]:
        extra.append(f"{m['issues']} ISSUES")
    if extra:
        y += 10
        parts.append(pill(" / ".join(extra), "#FFD43B", y))
        y += 36
    title = f"// CONTRIBUTION ACTIVITY - {m['label'].upper()}"
    return full_card(y + 20, "#74C0FC", title, "".join(parts))


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
    (out / "header.svg").write_text(render_header(data.get("avatar")), encoding="utf-8")
    if data.get("calendar"):
        (out / "contrib.svg").write_text(render_contrib(data["calendar"]), encoding="utf-8")
    if data.get("month"):
        (out / "activity.svg").write_text(render_activity(data["month"]), encoding="utf-8")
    print(f"Wrote cards to {out}/")


if __name__ == "__main__":
    main()
