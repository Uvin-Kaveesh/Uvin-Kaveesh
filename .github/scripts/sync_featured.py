"""Sync the profile's featured cards with the checkbox issue.

Run in the profile repository via .github/workflows/featured-projects.yml.
"""

import html
import json
import os
import re
import textwrap
import urllib.request
from pathlib import Path


OWNER = "Uvin-Kaveesh"
PROFILE_REPO = f"{OWNER}/{OWNER}"
ISSUE_NUMBER = 1
START = "<!-- featured-project-selector:start -->"
END = "<!-- featured-project-selector:end -->"
CHECKBOX = re.compile(r"^- \[([ xX])\] `([A-Za-z0-9_.-]+)`$", re.MULTILINE)
CARD_ASSETS = {
    "LeoLoom": "leoloom-smooth.gif",
    "Digital_Thermometer": "thermometer-smooth.gif",
    "SignalForge": "signalforge-smooth.gif",
    "CSE-AGM": "cse_agm-smooth.gif",
    "BCD-Arithmetic-Mini-Processor": "bcd-smooth.gif",
    "CSE-Drone-Project": "drone-smooth.gif",
    "PAPI-Based-Automated-Flight-Landing-System": "papi-smooth.gif",
}


def api(path, method="GET", data=None):
    token = os.environ["GH_TOKEN"]
    payload = None if data is None else json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.github.com{path}", data=payload, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "featured-project-selector",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def public_repos():
    repos = {}
    page = 1
    while True:
        batch = api(f"/users/{OWNER}/repos?type=owner&per_page=100&page={page}")
        for repo in batch:
            if repo["name"] != OWNER and not repo["private"] and not repo["fork"] and not repo["archived"]:
                repos[repo["name"]] = repo
        if len(batch) < 100:
            break
        page += 1
    return repos


def reconcile_issue(body, repos):
    if body.count(START) != 1 or body.count(END) != 1:
        raise ValueError("Selector issue markers are missing or duplicated")
    before, tail = body.split(START, 1)
    _, after = tail.split(END, 1)
    current = [(name, mark.lower() == "x") for mark, name in CHECKBOX.findall(tail.split(END, 1)[0])]
    seen = set()
    items = []
    for name, checked in current:
        if name in repos and name not in seen:
            items.append((name, checked))
            seen.add(name)
    items.extend((name, False) for name in sorted(repos, key=str.casefold) if name not in seen)
    checklist = "\n".join(f"- [{'x' if checked else ' '}] `{name}`" for name, checked in items)
    updated = before + START + "\n" + checklist + "\n" + END + after
    return updated, [name for name, checked in items if checked]


def generic_svg(repo):
    name = html.escape(repo["name"])
    desc = (repo.get("description") or "Project repository").strip()
    lines = textwrap.wrap(desc, width=44, max_lines=2, placeholder="…")
    description = "".join(
        f'<text x="48" y="{175 + i * 28}" fill="#c7dfe6" font-size="18">{html.escape(line)}</text>'
        for i, line in enumerate(lines)
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="640" height="350" viewBox="0 0 640 350">
<defs><linearGradient id="g" x2="1" y2="1"><stop stop-color="#111d34"/><stop offset="1" stop-color="#0b736e"/></linearGradient></defs>
<rect width="640" height="350" rx="22" fill="url(#g)"/>
<circle cx="550" cy="80" r="110" fill="#42dfd2" opacity=".10"/>
<rect x="15" y="15" width="610" height="320" rx="20" fill="none" stroke="#75c2da" stroke-width="2"/>
<text x="48" y="62" fill="#79e8e2" font-size="14" font-family="Arial, sans-serif">PROJECT</text>
<text x="48" y="128" fill="white" font-size="28" font-weight="bold" font-family="Arial, sans-serif">{name}</text>
{description}
<rect x="30" y="284" width="580" height="40" rx="12" fill="#09212e"/>
<text x="47" y="311" fill="white" font-size="18" font-family="Arial, sans-serif">Open project repository</text>
</svg>'''


def render_cards(selected, repos, root):
    previews = root / "assets" / "project-previews"
    generated = previews / "generated"
    cards = []
    for name in selected:
        if name in CARD_ASSETS:
            asset = CARD_ASSETS[name]
            if not (previews / asset).is_file():
                raise FileNotFoundError(previews / asset)
            source = f"./assets/project-previews/{asset}"
        else:
            generated.mkdir(parents=True, exist_ok=True)
            asset = f"{name}.svg"
            (generated / asset).write_text(generic_svg(repos[name]), encoding="utf-8")
            source = f"./assets/project-previews/generated/{asset}"
        url = f"https://github.com/{OWNER}/{name}"
        alt = html.escape(f"{name} project preview", quote=True)
        cards.append(f'  <a href="{url}"><img src="{source}" alt="{alt}" width="48%" /></a>')
    rows = ["<p align=\"center\">\n" + "\n".join(cards[i:i+2]) + "\n</p>" for i in range(0, len(cards), 2)]
    intro = "## Featured projects\n\nClick a project card to open its repository. [Choose which cards appear](https://github.com/Uvin-Kaveesh/Uvin-Kaveesh/issues/1). The CSE AGM preview is an illustration."
    return intro + ("\n\n" + "\n\n".join(rows) if rows else "\n\nNo projects selected yet.") + "\n\n"


def replace_featured(readme, section):
    start = readme.index("## Featured projects\n")
    end = readme.index("## Tools and technologies\n", start)
    return readme[:start] + section + readme[end:]


def main():
    root = Path(__file__).resolve().parents[2]
    repos = public_repos()
    issue = api(f"/repos/{PROFILE_REPO}/issues/{ISSUE_NUMBER}")
    updated_issue, selected = reconcile_issue(issue["body"], repos)
    if updated_issue != issue["body"]:
        api(f"/repos/{PROFILE_REPO}/issues/{ISSUE_NUMBER}", "PATCH", {"body": updated_issue})
    readme_path = root / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    updated_readme = replace_featured(readme, render_cards(selected, repos, root))
    if updated_readme != readme:
        readme_path.write_text(updated_readme, encoding="utf-8")
    print(f"Found {len(repos)} public projects; displaying {len(selected)} cards")


if __name__ == "__main__":
    main()

