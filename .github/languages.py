"""Render languages.svg: language mix across every repo I commit to, private and org included.

Each repo's GitHub language breakdown is weighted by my commit count there.
Needs GH_TOKEN (classic PAT: repo, read:org). Stdlib only. `--test` runs the self-check.
"""
import json, os, sys, urllib.request
from xml.sax.saxutils import escape

IGNORED = {"HTML", "CSS", "SCSS", "Jupyter Notebook", "ShaderLab", "Makefile", "Dockerfile", "Batchfile"}
LIMIT = 8

QUERY = """query($cursor: String, $uid: ID!) {
  viewer {
    repositories(first: 50, after: $cursor, isFork: false,
                 affiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER],
                 ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER]) {
      pageInfo { hasNextPage endCursor }
      nodes {
        languages(first: 20) { edges { size node { name color } } }
        defaultBranchRef { target { ... on Commit { history(author: {id: $uid}) { totalCount } } } }
      }
    }
  }
}"""


def gql(query, **variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        json.dumps({"query": query, "variables": variables}).encode(),
        {"Authorization": f"bearer {os.environ['GH_TOKEN']}"},
    )
    body = json.load(urllib.request.urlopen(req))
    if "errors" in body:
        sys.exit(f"GraphQL error: {body['errors']}")
    return body["data"]


def fetch():
    uid = gql("{ viewer { id } }")["viewer"]["id"]
    repos, cursor = [], None
    while True:
        page = gql(QUERY, cursor=cursor, uid=uid)["viewer"]["repositories"]
        for r in page["nodes"]:
            commits = ((r["defaultBranchRef"] or {}).get("target") or {}).get("history", {}).get("totalCount", 0)
            langs = [(e["node"]["name"], e["node"]["color"], e["size"]) for e in r["languages"]["edges"]]
            repos.append((commits, langs))
        if not page["pageInfo"]["hasNextPage"]:
            return repos
        cursor = page["pageInfo"]["endCursor"]


def shares(repos):
    """[(my_commits, [(lang, color, bytes)])] -> [(lang, color, fraction)], top LIMIT plus Other."""
    score, colors = {}, {}
    for commits, langs in repos:
        langs = [l for l in langs if l[0] not in IGNORED]
        total = sum(size for _, _, size in langs)
        if not commits or not total:
            continue
        for name, color, size in langs:
            score[name] = score.get(name, 0) + commits * size / total
            colors[name] = color or "#8b949e"
    grand = sum(score.values())
    ranked = sorted(score.items(), key=lambda kv: -kv[1])
    out = [(n, colors[n], s / grand) for n, s in ranked[:LIMIT]]
    rest = sum(s for _, s in ranked[LIMIT:]) / grand if grand else 0
    if rest >= 0.005:
        out.append(("Other", "#8b949e", rest))
    return out


def svg(rows):
    w, x0, bar_w = 480, 24, 432
    h = 86 + 26 * ((len(rows) + 1) // 2)
    parts, x = [], x0
    for name, color, f in rows:
        seg = bar_w * f
        parts.append(f'<rect x="{x:.1f}" y="52" width="{seg:.1f}" height="10" fill="{color}"/>')
        x += seg
    for i, (name, color, f) in enumerate(rows):
        cx, cy = x0 + (i % 2) * 216, 92 + (i // 2) * 26
        parts.append(f'<circle cx="{cx + 5}" cy="{cy - 4}" r="5" fill="{color}"/>'
                     f'<text x="{cx + 16}" y="{cy}" class="t">{escape(name)} <tspan class="m">{f:.1%}</tspan></text>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="Languages I write">
<style>
.t{{font:600 13px -apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;fill:#1f2328}}
.m{{font-weight:400;fill:#59636e}} .h{{font-size:15px}} .bg{{fill:#ffffff;stroke:#d1d9e0}}
@media (prefers-color-scheme: dark){{.t{{fill:#f0f6fc}} .m{{fill:#9198a1}} .bg{{fill:#0d1117;stroke:#3d444d}}}}
</style>
<rect class="bg" x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="6"/>
<text x="{x0}" y="34" class="t h">Languages I write <tspan class="m">· by my commits across all repos</tspan></text>
<clipPath id="c"><rect x="{x0}" y="52" width="{bar_w}" height="10" rx="5"/></clipPath>
<g clip-path="url(#c)">{''.join(p for p in parts if p.startswith('<rect'))}</g>
{''.join(p for p in parts if p.startswith('<circle'))}
</svg>
"""


def test():
    rows = shares([(10, [("Rust", "#dea584", 900), ("HTML", "#e34c26", 5000), ("Svelte", "#ff3e00", 100)]),
                   (0, [("Go", "#00ADD8", 999)]),  # no commits of mine -> ignored
                   (5, [("Go", "#00ADD8", 50)])])
    got = {n: round(f, 3) for n, _, f in rows}
    assert got == {"Rust": 0.6, "Go": 0.333, "Svelte": 0.067}, got
    assert "HTML" not in svg(rows) and "Rust" in svg(rows)
    print("ok")


if __name__ == "__main__":
    test() if "--test" in sys.argv else sys.stdout.write(svg(shares(fetch())))
