#!/usr/bin/env python3
"""
Scrapes upcoming (and recently played) matches for Valur's U19 A and B teams
from ksi.is and writes them to data.json for the front-end page to display.

APPROACH
--------
Each competition page on ksi.is has a "Leikir og urslit" (matches & results)
view that lists fixtures grouped under date headings, in plain server-rendered
HTML (no JavaScript needed). We read the page top-to-bottom as a sequence of
text lines, keep track of the most recently seen date / kickoff-time / venue
as we go, and whenever we hit a line that looks like "Team A - Team B" and
contains the word "Valur", we record a match using whatever date/time/venue
context we've seen most recently above it.

This mirrors how a person would read the page, and is intentionally simple:
no guessing at CSS class names, just "find the lines that mention Valur and
note what's around them."
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup, NavigableString

BLOCK_TAGS = {
    "div", "p", "li", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6",
    "section", "article", "header", "footer", "ul", "ol", "table", "br",
    "main", "nav", "form", "fieldset",
}


def block_aware_lines(root):
    """
    A get_text() replacement that behaves more like what a browser would
    visually render as separate lines: block-level tags (div, li, tr, ...)
    start a new line, but inline tags (a, span, ...) and bare text stay on
    the same line. This matters because ksi.is renders each match's two
    team names as two separate <a> tags with a plain '-' text node between
    them, all inside one block container -- get_text("\\n", ...) would
    otherwise split that onto three separate lines and break the "Team A -
    Team B" pattern we search for.
    """
    lines = []
    buf = []

    def flush():
        if buf:
            s = re.sub(r"\s+", " ", " ".join(buf)).strip()
            if s:
                lines.append(s)
            buf.clear()

    def walk(node):
        for child in node.children:
            if isinstance(child, NavigableString):
                txt = str(child).strip()
                if txt:
                    buf.append(txt)
            elif child.name in BLOCK_TAGS:
                flush()
                walk(child)
                flush()
            else:
                walk(child)

    walk(root)
    flush()
    return lines

# ---------------------------------------------------------------------------
# Configuration: the two competition pages to scrape
# ---------------------------------------------------------------------------
COMPETITIONS = [
    {
        "team": "A",
        "label": "Valur U19 A",
        "id": "7015358",
    },
    {
        "team": "B",
        "label": "Valur U19 B",
        "id": "7017555",
    },
]

BASE = "https://www.ksi.is/oll-mot/mot"
# Variants we attempt per competition: upcoming fixtures (paginated) and the
# "results" toggle (also paginated), in case that view is server-rendered too.
PAGE_VARIANTS = [
    {"toggle": None, "page": None},
    {"toggle": None, "page": 2},
    {"toggle": "results", "page": None},
    {"toggle": "results", "page": 2},
]

OUTPUT_PATH = Path(__file__).parent / "data.json"
MAX_AGE_PAST_DAYS = 21   # don't keep results older than this
MAX_AHEAD_DAYS = 120     # don't keep fixtures further out than this

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ValurFixturesBot/1.0; "
        "personal non-commercial use)"
    )
}

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "maí": 5, "mai": 5,
    "jún": 6, "jun": 6, "júl": 7, "jul": 7, "ágú": 8, "agu": 8,
    "sep": 9, "okt": 10, "nóv": 11, "nov": 11, "des": 12,
}
DATE_RE = re.compile(r"(\d{1,2})\.\s*([a-záðéíóúýþæö]{3,4})\.?", re.IGNORECASE)
TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\b")
SCORE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*-\s*(\d{1,2})(?!\d)")
MATCHUP_SPLIT_RE = re.compile(r"\s-\s")


def build_url(comp_id, toggle=None, page=None):
    url = f"{BASE}?id={comp_id}&banner-tab=matches-and-results"
    if toggle:
        url += f"&toggle={toggle}"
    if page:
        url += f"&page={page}"
    return url


def parse_date(text, year):
    m = DATE_RE.search(text.lower())
    if not m:
        return None
    day = int(m.group(1))
    month = MONTHS.get(m.group(2)[:3])
    if not month:
        return None
    try:
        return f"{year:04d}-{month:02d}-{day:02d}"
    except ValueError:
        return None


def split_matchup(line):
    """Split a 'Team A - Team B' line into two team-name strings."""
    parts = MATCHUP_SPLIT_RE.split(line, maxsplit=1)
    if len(parts) != 2:
        return None, None
    return parts[0].strip(), parts[1].strip()


def split_matchup_with_score(line, score_match):
    """For a finished-match line like 'Team A 2 - 1 Team B', split around
    the score itself rather than a literal ' - ' (team names can legally
    contain digits/dashes, e.g. 'Valur/KH/Fálkar 2')."""
    team_a = line[:score_match.start()].strip()
    team_b = line[score_match.end():].strip()
    return team_a or None, team_b or None


def dedupe_repeated_name(s):
    """ksi.is repeats each team's name twice in a row (once for the crest
    alt-text, once for the visible label), e.g. 'Valur/KH/Fálkar
    Valur/KH/Fálkar' or 'Valur/KH/Fálkar 2 Valur/KH/Fálkar 2'. Collapse
    that down to a single copy."""
    s = s.strip()
    tokens = s.split(" ")
    for k in range(1, len(tokens)):
        first = " ".join(tokens[:k])
        rest = " ".join(tokens[k:])
        if first and first == rest:
            return first
    return s


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    return r.text


def scrape_variant(comp, toggle, page, year):
    url = build_url(comp["id"], toggle=toggle, page=page)
    try:
        html = fetch(url)
    except requests.RequestException as exc:
        print(f"[warn] failed to fetch {url}: {exc}", file=sys.stderr)
        return []

    soup = BeautifulSoup(html, "html.parser")
    # remove nav/header/footer chrome so we don't accidentally scan menu links
    for tag in soup.find_all(["nav", "header", "footer", "script", "style"]):
        tag.decompose()

    lines = block_aware_lines(soup)

    matches = []
    current_date = None
    current_time = None
    current_venue = None
    # state machine tracking where we are relative to the most recent
    # "datetime" line, since venue/competition-name/matchup lines can't be
    # reliably told apart by content alone (venues can contain ' - ' too)
    state = "idle"  # idle -> expect_venue -> expect_matchup

    for line in lines:
        date_found = parse_date(line, year)
        time_found = TIME_RE.search(line)
        lower = line.lower()
        is_comp_name_line = lower.startswith("íslandsmót") or lower.startswith("islandsmot")

        if date_found and time_found:
            current_date = date_found
            current_time = time_found.group(1)
            current_venue = None
            state = "expect_venue"
            continue

        if date_found and not time_found:
            current_date = date_found
            state = "idle"
            continue

        if state == "expect_venue":
            current_venue = line
            state = "expect_matchup"
            continue

        if state == "expect_matchup":
            if is_comp_name_line:
                continue  # keep waiting, this is the competition-name link
            # this line is the matchup line, whether or not it mentions Valur
            state = "idle"
            if "valur" not in lower:
                continue

            score_match = SCORE_RE.search(line)
            score = None
            status = "scheduled"
            if score_match:
                score = f"{score_match.group(1)}-{score_match.group(2)}"
                status = "finished"
                team_a, team_b = split_matchup_with_score(line, score_match)
            else:
                team_a, team_b = split_matchup(line)

            if not team_a or not team_b:
                continue

            team_a = dedupe_repeated_name(team_a)
            team_b = dedupe_repeated_name(team_b)

            matches.append({
                "team": comp["team"],
                "team_label": comp["label"],
                "date": current_date,
                "time": current_time if not score else None,
                "status": status,
                "score": score,
                "home_team": team_a,
                "away_team": team_b,
                "valur_is_home": "valur" in team_a.lower(),
                "venue": current_venue,
            })

    return matches


def scrape_competition(comp):
    year = datetime.now(timezone.utc).year
    all_matches = []
    for variant in PAGE_VARIANTS:
        found = scrape_variant(comp, variant["toggle"], variant["page"], year)
        all_matches.extend(found)
    return all_matches


def dedupe(matches):
    seen = set()
    out = []
    for m in matches:
        key = (m.get("team"), m.get("date"), m.get("home_team"), m.get("away_team"))
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out


def within_window(m, today):
    if not m.get("date"):
        return True  # keep undated entries rather than silently drop them
    try:
        d = datetime.strptime(m["date"], "%Y-%m-%d").date()
    except ValueError:
        return True
    delta_days = (d - today).days
    return -MAX_AGE_PAST_DAYS <= delta_days <= MAX_AHEAD_DAYS


def main():
    today = datetime.now(timezone.utc).date()
    all_matches = []
    for comp in COMPETITIONS:
        comp_matches = scrape_competition(comp)
        print(f"[info] {comp['label']}: found {len(comp_matches)} raw match mentions")
        all_matches.extend(comp_matches)

    all_matches = dedupe(all_matches)
    all_matches = [m for m in all_matches if within_window(m, today)]
    all_matches.sort(key=lambda m: (m.get("date") or "9999-99-99", m.get("time") or "99:99"))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "matches": all_matches,
    }

    if not all_matches and OUTPUT_PATH.exists():
        print("[warn] no matches found this run -- keeping previous data.json", file=sys.stderr)
        return

    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[info] wrote {len(all_matches)} matches to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
