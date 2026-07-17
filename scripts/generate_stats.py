#!/usr/bin/env python3
"""Generate a GitHub stats card as an SVG.

Runs in GitHub Actions with the built-in GITHUB_TOKEN — no external
service, no PAT to manage. Writes generated/overview.svg, which the
profile README embeds directly.

Env vars:
    GITHUB_TOKEN  required, used for the GraphQL API
    GH_LOGIN      GitHub username (default: Thakur-Prateek)
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

API = "https://api.github.com/graphql"

QUERY = """
query ($login: String!, $cursor: String) {
  user(login: $login) {
    name
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    repositoriesContributedTo(
      first: 1
      contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, REPOSITORY]
    ) { totalCount }
    repositories(ownerAffiliations: OWNER, first: 100, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      nodes { stargazerCount }
    }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
    }
  }
}
"""

# tokyonight palette, matching the streak card next to this one
BG = "#1a1b27"
TITLE = "#70a5fd"
ICON = "#bf91f3"
TEXT = "#38bdae"


def gql(token: str, variables: dict) -> dict:
    body = json.dumps({"query": QUERY, "variables": variables}).encode()
    req = urllib.request.Request(
        API,
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-stats-card",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")
    return data["data"]["user"]


def fetch_stats(token: str, login: str) -> dict:
    user = gql(token, {"login": login, "cursor": None})
    stars = sum(n["stargazerCount"] for n in user["repositories"]["nodes"])
    page = user["repositories"]["pageInfo"]
    while page["hasNextPage"]:
        more = gql(token, {"login": login, "cursor": page["endCursor"]})
        stars += sum(n["stargazerCount"] for n in more["repositories"]["nodes"])
        page = more["repositories"]["pageInfo"]

    contrib = user["contributionsCollection"]
    return {
        "name": user["name"] or login,
        "stars": stars,
        "commits": contrib["totalCommitContributions"]
        + contrib["restrictedContributionsCount"],
        "prs": user["pullRequests"]["totalCount"],
        "issues": user["issues"]["totalCount"],
        "contributed": user["repositoriesContributedTo"]["totalCount"],
        "followers": user["followers"]["totalCount"],
    }


def fmt(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


# Minimal 16x16 stroke icons, drawn at the row's origin.
ICONS = {
    "star": '<path d="M8 1.5l2 4.1 4.5.6-3.3 3.2.8 4.5L8 11.8l-4 2.1.8-4.5L1.5 6.2 6 5.6z" fill="none" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"/>',
    "commit": '<circle cx="8" cy="8" r="3.2" fill="none" stroke="{c}" stroke-width="1.4"/><path d="M0.5 8h4M11.5 8h4" stroke="{c}" stroke-width="1.4"/>',
    "pr": '<circle cx="4" cy="3.5" r="2" fill="none" stroke="{c}" stroke-width="1.4"/><circle cx="4" cy="12.5" r="2" fill="none" stroke="{c}" stroke-width="1.4"/><circle cx="12" cy="12.5" r="2" fill="none" stroke="{c}" stroke-width="1.4"/><path d="M4 5.5v5M12 10.5V7a3 3 0 0 0-3-3H8" fill="none" stroke="{c}" stroke-width="1.4"/>',
    "issue": '<circle cx="8" cy="8" r="6" fill="none" stroke="{c}" stroke-width="1.4"/><circle cx="8" cy="8" r="1.6" fill="{c}"/>',
    "repo": '<rect x="2.5" y="1.5" width="11" height="13" rx="1.5" fill="none" stroke="{c}" stroke-width="1.4"/><path d="M5.5 4.5h5M5.5 7h5" stroke="{c}" stroke-width="1.4"/>',
    "people": '<circle cx="8" cy="5" r="2.8" fill="none" stroke="{c}" stroke-width="1.4"/><path d="M2.5 14.5a5.5 5.5 0 0 1 11 0" fill="none" stroke="{c}" stroke-width="1.4"/>',
}


def render(stats: dict) -> str:
    # issues / contributed-to only earn a row once they're non-zero
    rows = [
        ("star", "Total stars earned", fmt(stats["stars"])),
        ("commit", "Commits (past year)", fmt(stats["commits"])),
        ("pr", "Total PRs", fmt(stats["prs"])),
        *([("issue", "Total issues", fmt(stats["issues"]))] if stats["issues"] else []),
        *([("repo", "Contributed to", fmt(stats["contributed"]))] if stats["contributed"] else []),
        ("people", "Followers", fmt(stats["followers"])),
    ]
    height = 62 + len(rows) * 25 + 18
    row_svg = []
    for i, (icon, label, value) in enumerate(rows):
        y = 62 + i * 25
        row_svg.append(
            f'<g class="row" style="animation-delay:{200 + i * 120}ms" '
            f'transform="translate(28,{y})">'
            f'<g transform="translate(0,-12)">{ICONS[icon].format(c=ICON)}</g>'
            f'<text x="26" y="0" class="label">{label}:</text>'
            f'<text x="364" y="0" text-anchor="end" class="value">{value}</text>'
            f"</g>"
        )
    rows_block = "\n    ".join(row_svg)

    return f"""<svg width="420" height="{height}" viewBox="0 0 420 {height}" fill="none"
     xmlns="http://www.w3.org/2000/svg" role="img"
     aria-label="{stats['name']}'s GitHub stats">
  <style>
    .title {{ font: 600 18px 'Segoe UI', Ubuntu, sans-serif; fill: {TITLE}; }}
    .label, .value {{ font: 400 14px 'Segoe UI', Ubuntu, sans-serif; fill: {TEXT}; }}
    .value {{ font-weight: 700; }}
    .row, .title {{ opacity: 0; animation: fadein 0.5s ease-in-out forwards; }}
    @keyframes fadein {{ to {{ opacity: 1; }} }}
  </style>
  <rect width="420" height="{height}" rx="8" fill="{BG}"/>
  <text x="28" y="35" class="title">{stats['name']}'s GitHub Stats</text>
  <g>
    {rows_block}
  </g>
</svg>
"""


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set")
    login = os.environ.get("GH_LOGIN", "Thakur-Prateek")

    stats = fetch_stats(token, login)
    print(f"stats for {login}: {stats}")

    out = Path(__file__).resolve().parent.parent / "generated" / "overview.svg"
    out.parent.mkdir(exist_ok=True)
    out.write_text(render(stats))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
