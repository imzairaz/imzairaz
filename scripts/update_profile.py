"""Render the profile card; --refresh updates public stats from GitHub."""

import argparse
import calendar
import hashlib
from datetime import date, datetime
import json
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
USERNAME = "imzairaz"


def uptime(today=None):
    today = today or datetime.now(ZoneInfo("Asia/Colombo")).date()
    birthday = date(2001, 10, 26)
    months = (today.year - birthday.year) * 12 + today.month - birthday.month

    def anniversary(offset):
        year, month = divmod(birthday.year * 12 + birthday.month - 1 + offset, 12)
        month += 1
        return date(year, month, min(birthday.day, calendar.monthrange(year, month)[1]))

    if anniversary(months) > today:
        months -= 1
    years, months_part = divmod(months, 12)
    days = (today - anniversary(months)).days
    return ", ".join(f"{n} {unit}{'' if n == 1 else 's'}" for n, unit in
                     [(years, "year"), (months_part, "month"), (days, "day")])


def fetch(path):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USERNAME}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    with urlopen(Request("https://api.github.com/" + path, headers=headers), timeout=30) as response:
        return json.load(response)


def refresh_stats():
    user = fetch("users/" + USERNAME)
    stars = 0
    page = 1
    while True:
        repos = fetch(f"users/{USERNAME}/repos?per_page=100&page={page}&type=owner")
        stars += sum(repo["stargazers_count"] for repo in repos)
        if len(repos) < 100:
            break
        page += 1
    stats = {"Repos": str(user["public_repos"]), "Stars": str(stars), "Followers": str(user["followers"])}
    if os.environ.get("GITHUB_TOKEN"):
        stats.update(detailed_stats())
    return stats


def graphql(query, variables):
    request = Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
                 "Content-Type": "application/json", "User-Agent": USERNAME},
    )
    with urlopen(request, timeout=60) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload["data"]


def detailed_stats():
    # Commit and line totals cover the user's commits on default branches
    # of public owned repositories. They are not a count of current file lines.
    identity = graphql('''query($login:String!) {
      user(login:$login) { id repositoriesContributedTo(includeUserRepositories:true) { totalCount } }
    }''', {"login": USERNAME})["user"]
    repositories = []
    cursor = None
    while True:
        result = graphql('''query($login:String!, $cursor:String) {
          user(login:$login) {
            repositories(first:100, after:$cursor, privacy:PUBLIC, ownerAffiliations:OWNER) {
              nodes { name }
              pageInfo { hasNextPage endCursor }
            }
          }
        }''', {"login": USERNAME, "cursor": cursor})["user"]["repositories"]
        repositories.extend(result["nodes"])
        if not result["pageInfo"]["hasNextPage"]:
            break
        cursor = result["pageInfo"]["endCursor"]
    additions = deletions = commits = 0
    for repository in repositories:
        cursor = None
        while True:
            result = graphql('''query($owner:String!, $name:String!, $author:ID!, $cursor:String) {
              repository(owner:$owner, name:$name) {
                defaultBranchRef { target { ... on Commit {
                  history(first:100, after:$cursor, author:{id:$author}) {
                    nodes { additions deletions }
                    pageInfo { hasNextPage endCursor }
                  }
                } } }
              }
            }''', {"owner": USERNAME, "name": repository["name"],
                   "author": identity["id"], "cursor": cursor})["repository"]
            branch = result["defaultBranchRef"]
            if not branch:
                break
            history = branch["target"]["history"]
            for commit in history["nodes"]:
                commits += 1
                additions += commit["additions"]
                deletions += commit["deletions"]
            if not history["pageInfo"]["hasNextPage"]:
                break
            cursor = history["pageInfo"]["endCursor"]
    return {"Contributed": str(identity["repositoriesContributedTo"]["totalCount"]),
            "Commits": str(commits), "Additions": str(additions),
            "Deletions": str(deletions), "LOC": str(additions - deletions)}


def render(theme, stats):
    dark = theme == "dark"
    bg, fg, key, value, muted = (
        ("#161b22", "#c9d1d9", "#ffa657", "#a5d6ff", "#616e7f")
        if dark else ("#f6f8fa", "#24292f", "#953800", "#0a3069", "#c2cfde")
    )
    parts = [f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="985" height="530" viewBox="0 0 985 530" role="img" aria-labelledby="title desc" font-family="ConsolasFallback,Consolas,monospace" font-size="16">
<title id="title">Zairaz's GitHub profile</title>
<desc id="desc">Full-stack developer specializing in MERN, backend architecture, and clean user interfaces. Contact: im.zairaz@gmail.com.</desc>
<style>@font-face{{src:local('Consolas'),local('Consolas Bold');font-family:'ConsolasFallback';font-display:swap;-webkit-size-adjust:109%;size-adjust:109%}} text,tspan{{white-space:pre}} .addColor{{fill:{"#3fb950" if dark else "#1a7f37"}}} .delColor{{fill:{"#f85149" if dark else "#cf222e"}}} .key{{fill:{key}}} .value{{fill:{value}}} .cc{{fill:{muted}}}</style>
<rect width="985" height="530" rx="15" fill="{bg}"/>
<g fill="{fg}">''']

    def text(x, y, content, css=""):
        parts.append(f'<text x="{x}" y="{y}" class="{css}">{escape(content)}</text>')

    parts.append('<g id="intro-panel">')
    text(35, 100, "$ whoami", "cc")
    parts.append('<g font-size="46" font-weight="700">')
    text(32, 158, "ZAIRAZ", "value")
    parts.append('</g>')
    parts.append('<g font-size="14">')
    text(35, 190, "FULL-STACK DEVELOPER", "key")
    parts.append('</g>')
    parts.append(f'<path d="M35 222H340" stroke="{muted}" stroke-opacity="0.45"/>')
    text(35, 264, "$ cat mindset.txt", "value")
    text(35, 304, "Build with purpose.")
    text(35, 332, "Keep it simple.")
    text(35, 360, "Make it work beautifully.")
    parts.append('<g font-size="14">')
    text(35, 426, "$ design && develop && deploy", "key")
    parts.append('</g>')
    text(35, 470, "$", "value")
    parts.append(f'<rect x="56" y="457" width="8" height="15" fill="{value}"/>')
    parts.append('</g>')

    def heading(y, label):
        text(390, y, label + " " + "─" * max(1, 59 - len(label)))

    def row(y, label, content, link=None):
        dots = " " + "." * max(2, 54 - len(label) - len(content)) + " "
        label_markup = '.'.join(f'<tspan class="key">{escape(part)}</tspan>' for part in label.split('.'))
        body = f'<text x="390" y="{y}"><tspan class="cc">. </tspan>{label_markup}:<tspan class="cc">{dots}</tspan><tspan class="value">{escape(content)}</tspan></text>'
        parts.append(f'<a href="{escape(link)}">{body}</a>' if link else body)

    heading(30, "zairaz@github")
    row(50, "OS", "macOS")
    row(70, "Uptime", uptime())
    row(90, "Host", "Welford Systems")
    row(110, "Kernel", "Full-Stack Developer")
    row(130, "IDE", "VS Code 1.142.0")
    row(170, "Languages.Programming", "JS, TS, Python, Java, C#, PHP")
    row(190, "Frameworks.Frontend", "Next.js, Vue, Angular, Tailwind")
    row(210, "Frameworks.Backend", "Express, Django, ASP.NET Core")
    row(250, "Databases", "MongoDB, MySQL, PostgreSQL")
    row(270, "Exploring", "Python, Django & Cloud Infrastructure")
    heading(310, "- Contact")
    row(330, "Email.Personal", "im.zairaz@gmail.com", "mailto:im.zairaz@gmail.com")
    row(350, "Portfolio", "zairaz.com", "https://zairaz.com")
    row(370, "LinkedIn", "in/zairaz", "https://linkedin.com/in/zairaz")
    row(390, "X", "@im_zairaz", "https://x.com/im_zairaz")
    row(410, "GitHub", USERNAME, "https://github.com/" + USERNAME)
    heading(450, "- GitHub Stats")
    def metric(label):
        raw = stats.get(label)
        return f"{int(raw):,}" if raw is not None else "—"

    def span(content, css=None):
        attribute = f' class="{css}"' if css else ''
        return f'<tspan{attribute}>{escape(content)}</tspan>'

    def stat_line(y, chunks):
        parts.append(f'<text x="390" y="{y}">' + ''.join(span(content, css) for content, css in chunks) + '</text>')

    def pad_metric(chunks, number, end_column):
        # The reference uses 60 monospace columns, with both pipes at column 37.
        width = max(0, end_column - sum(len(content) for content, _ in chunks) - len(number))
        dots = ' ' + '.' * (width - 2) + ' ' if width >= 3 else ('. ' if width == 2 else '.' * width)
        chunks.extend([(dots, "cc"), (number, "value")])

    repo, contributed, stars = (metric(label) for label in ("Repos", "Contributed", "Stars"))
    repos_line = [(". ", "cc"), ("Repos", "key"), (":", None)]
    contribution_suffix = f" {{Contributed: {contributed}}}"
    pad_metric(repos_line, repo, 35 - len(contribution_suffix))
    repos_line.extend([(" {", None), ("Contributed", "key"), (": ", None),
                       (contributed, "value"), ("} | ", None), ("Stars", "key"), (":", None)])
    pad_metric(repos_line, stars, 60)
    stat_line(470, repos_line)

    commits_line = [(". ", "cc"), ("Commits", "key"), (":", None)]
    pad_metric(commits_line, metric("Commits"), 35)
    commits_line.extend([(" | ", None), ("Followers", "key"), (":", None)])
    pad_metric(commits_line, metric("Followers"), 60)
    stat_line(490, commits_line)
    parts.append('<g><title>Commit and line totals: authored commits on default branches of public owned repositories. A dash means unavailable.</title>')
    code_line = [(". ", "cc"), ("Lines of Code on GitHub", "key"), (":", None)]
    pad_metric(code_line, metric("LOC"), 34)
    code_line.extend([(" ( ", None), (metric("Additions").rjust(7) + "++", "addColor"),
                      (", ", None), (metric("Deletions").rjust(8) + "--", "delColor"), (" )", None)])
    stat_line(510, code_line)
    parts.append('</g>')
    parts.append("</g></svg>\n")
    return "\n".join(parts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    cache = ROOT / "assets/profile-stats.json"
    stats = refresh_stats() if args.refresh else json.loads(cache.read_text()) if cache.exists() else {}
    if args.refresh:
        cache.write_text(json.dumps(stats, indent=2) + "\n")
    for theme in ("dark", "light"):
        (ROOT / f"{theme}_mode.svg").write_text(render(theme, stats))
    # Change the image URL when its contents change to refresh cached embeds.
    version = hashlib.sha256(
        (ROOT / "dark_mode.svg").read_bytes() + (ROOT / "light_mode.svg").read_bytes()
    ).hexdigest()[:12]
    readme = ROOT / "README.md"
    image_base = f"https://raw.githubusercontent.com/{USERNAME}/{USERNAME}/master/"
    readme.write_text(re.sub(
        r'((?:src|srcset)=")(?:https://raw\.githubusercontent\.com/[^/]+/[^/]+/[^/]+/)?'
        r'((?:dark|light)_mode\.svg)(?:\?[^\"]*)?(")',
        lambda match: match[1] + image_base + match[2] + "?v=" + version + match[3],
        readme.read_text(),
    ))
