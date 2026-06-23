#!/usr/bin/env python3
"""
Diagnostic script -- run this to figure out where the scraper is breaking.
Usage:  python debug_scraper.py
"""
import requests
from scraper import block_aware_lines, BASE
from bs4 import BeautifulSoup
 
URL = f"{BASE}?id=7015358&banner-tab=matches-and-results"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ValurFixturesBot/1.0; personal non-commercial use)"}
 
print(f"Fetching: {URL}")
r = requests.get(URL, headers=HEADERS, timeout=25)
 
print(f"Status code: {r.status_code}")
print(f"requests-guessed encoding: {r.encoding}")
print(f"Response length: {len(r.content)} bytes")
print(f"'valur' appears in raw bytes: {r.content.lower().count(b'valur')} times")
 
# Save the raw bytes so we can inspect it directly if needed
with open("debug_output.html", "wb") as f:
    f.write(r.content)
print("Saved full response to debug_output.html")
 
soup = BeautifulSoup(r.content, "html.parser")
print(f"BeautifulSoup-detected encoding: {soup.original_encoding}")
for tag in soup.find_all(["nav", "header", "footer", "script", "style"]):
    tag.decompose()
 
lines = block_aware_lines(soup)
print(f"\nTotal extracted lines: {len(lines)}")
 
print("\n--- First 40 lines ---")
for l in lines[:40]:
    print(repr(l))
 
print("\n--- Lines containing 'valur' ---")
valur_lines = [l for l in lines if "valur" in l.lower()]
if not valur_lines:
    print("(none found)")
else:
    for l in valur_lines:
        print(repr(l))