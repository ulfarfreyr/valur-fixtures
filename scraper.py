#!/usr/bin/env python3
"""
Scrapes upcoming (and recently played) matches for Valur youth teams from
ksi.is and writes them to data.json for the front-end page to display.

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
from datetime import date, datetime, timezone
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
# Configuration: competition pages to scrape
# ---------------------------------------------------------------------------
COMPETITIONS = [
    {
        "profile": "jon",
        "profile_label": "Jon",
        "age_group": "U19",
        "team": "A",
        "label": "Valur U19 A",
        "id": "7015358",
    },
    {
        "profile": "jon",
        "profile_label": "Jon",
        "age_group": "U19",
        "team": "B",
        "label": "Valur U19 B",
        "id": "7017555",
    },
    {
        "profile": "stefan",
        "profile_label": "Stefan",
        "age_group": "U16",
        "team": "A",
        "label": "Valur U16 A",
        "id": "7019110",
    },
    {
        "profile": "stefan",
        "profile_label": "Stefan",
        "age_group": "U16",
        "team": "B",
        "label": "Valur U16 B",
        "id": "7090279",
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


def parse_date(text, reference_date):
    m = DATE_RE.search(text.lower())
    if not m:
        return None
    day = int(m.group(1))
    month = MONTHS.get(m.group(2)[:3])
    if not month:
        return None
    candidates = []
    for y in (reference_date.year - 1, reference_date.year, reference_date.year + 1):
        try:
            candidates.append(date(y, month, day))
        except ValueError:
            continue
    if not candidates:
        return None
    best = min(candidates, key=lambda d: abs((d - reference_date).days))
    return best.isoformat()


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


def looks_like_matchup_line(line):
    return bool(SCORE_RE.search(line) or MATCHUP_SPLIT_RE.search(line))


def is_unconfirmed_marker_line(lower):
    return lower == "óstaðfest" or lower.startswith("óstaðfest ") or lower == "ostadfest"


def extract_match_from_line(comp, line, current_date, current_time, current_venue):
    lower = line.lower()
    if "valur" not in lower:
        return None

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
        return None

    team_a = dedupe_repeated_name(team_a)
    team_b = dedupe_repeated_name(team_b)

    return {
        "profile": comp["profile"],
        "profile_label": comp["profile_label"],
        "age_group": comp["age_group"],
        "competition_id": comp["id"],
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
    }


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    # Return raw bytes rather than r.text -- requests sometimes guesses the
    # wrong charset when the server doesn't send an explicit Content-Type
    # charset, producing mojibake (e.g. "jÃºnÃ­" instead of "júní"). Passing
    # bytes lets BeautifulSoup detect encoding from the page's own
    # <meta charset> tag instead, which is far more reliable here.
    return r.content


def scrape_variant(comp, toggle, page, reference_date):
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
    pending_team = None
    pending_score = None
    # state machine tracking where we are relative to the most recent
    # "datetime" line, since venue/competition-name/matchup lines can't be
    # reliably told apart by content alone (venues can contain ' - ' too)
    state = "idle"  # idle -> expect_venue -> expect_matchup

    for line in lines:
        date_found = parse_date(line, reference_date)
        time_found = TIME_RE.search(line)
        lower = line.lower()
        is_comp_name_line = lower.startswith("íslandsmót") or lower.startswith("islandsmot")
        is_unconfirmed_line = is_unconfirmed_marker_line(lower)

        if date_found and time_found:
            current_date = date_found
            current_time = time_found.group(1)
            current_venue = None
            pending_team = None
            pending_score = None
            state = "expect_venue"
            continue

        if date_found and not time_found:
            current_date = date_found
            pending_team = None
            pending_score = None
            state = "idle"
            continue

        if is_unconfirmed_line:
            continue

        if state == "expect_venue":
            if is_comp_name_line:
                continue
            if looks_like_matchup_line(line):
                state = "idle"
                match = extract_match_from_line(comp, line, current_date, current_time, current_venue)
                if match:
                    matches.append(match)
                continue
            current_venue = line
            pending_team = None
            pending_score = None
            state = "expect_matchup"
            continue

        if state == "expect_matchup":
            if is_comp_name_line:
                continue  # keep waiting, this is the competition-name link
            # Matchups can appear either in one line ("Team A - Team B") or
            # as three lines ("Team A", "-", "Team B").
            if line == "-":
                continue

            if pending_team and not pending_score and SCORE_RE.fullmatch(line.strip()):
                pending_score = line.strip()
                continue

            if pending_team:
                if pending_score:
                    combined = f"{pending_team} {pending_score} {line}"
                else:
                    combined = f"{pending_team} - {line}"
                pending_team = None
                pending_score = None
                state = "idle"
                match = extract_match_from_line(comp, combined, current_date, current_time, current_venue)
                if match:
                    matches.append(match)
                continue

            if looks_like_matchup_line(line):
                state = "idle"
                match = extract_match_from_line(comp, line, current_date, current_time, current_venue)
                if match:
                    matches.append(match)
                continue

            pending_team = line
            pending_score = None
            continue

    return matches


def scrape_competition(comp, reference_date):
    all_matches = []
    for variant in PAGE_VARIANTS:
        found = scrape_variant(comp, variant["toggle"], variant["page"], reference_date)
        all_matches.extend(found)
    return all_matches


def dedupe(matches):
    by_key = {}

    def quality(m):
        return (
            2 if m.get("score") else 0,
            1 if m.get("time") else 0,
            1 if m.get("venue") else 0,
            1 if m.get("status") == "finished" else 0,
        )

    for m in matches:
        key = (
            m.get("profile"),
            m.get("age_group"),
            m.get("team"),
            m.get("date"),
            m.get("home_team"),
            m.get("away_team"),
        )
        existing = by_key.get(key)
        if existing is None or quality(m) > quality(existing):
            by_key[key] = m
    return list(by_key.values())


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
        comp_matches = scrape_competition(comp, today)
        print(f"[info] {comp['label']}: found {len(comp_matches)} raw match mentions")
        all_matches.extend(comp_matches)

    all_matches = dedupe(all_matches)
    all_matches = [m for m in all_matches if within_window(m, today)]
    all_matches.sort(key=lambda m: (m.get("date") or "9999-99-99", m.get("time") or "99:99"))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "matches": all_matches,
    }

    if not all_matches:
        print("[warn] no matches found this run", file=sys.stderr)
        payload["warnings"] = ["No matches were found in this scrape run."]

    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[info] wrote {len(all_matches)} matches to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()