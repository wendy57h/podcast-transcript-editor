"""Offline checks for the skill's default layout; never verifies transcript truth."""
import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

HEADINGS = ["开篇简介", "嘉宾核心洞察", "全文文本"]
BLUE = {"blue", "rgb(36,91,219)", "#245bdb"}
BLACK = {"", "black", "rgb(0,0,0)", "#000000"}


def content_of(path):
    raw = path.read_text(encoding="utf-8-sig")
    if raw.lstrip().startswith("{"):
        response = json.loads(raw)
        if response.get("ok") is not True:
            raise ValueError("fetch JSON must report ok=true")
        raw = response["data"]["document"]["content"]
    if "<!DOCTYPE" in raw.upper() or "<!ENTITY" in raw.upper():
        raise ValueError("DTD/entity declarations are unsupported")
    raw = re.sub(r"^\s*<\?xml[^?]*\?>", "", raw, count=1)
    root = ET.fromstring("<root>" + raw + "</root>")
    if len(root) == 1 and root[0].tag in {"root", "document", "doc"}:
        root = root[0]
    return root


def text_of(element):
    return "".join(element.itertext())


def normalize_color(value):
    return value.lower().replace(" ", "")


def styled_text(element, bold=False, color=""):
    """Yield text with effective ancestor styles, including child tails."""
    bold = bold or element.tag in {"b", "strong"}
    color = normalize_color(element.attrib.get("text-color", color))
    if element.text:
        yield element.text, bold, color
    for child in element:
        yield from styled_text(child, bold, color)
        if child.tail:
            yield child.tail, bold, color


def check(root, hosts, guests=(), episode_url=None):
    errors = []
    warnings = []
    children = list(root)
    h2 = [e for e in children if e.tag == "h2"]
    if [text_of(e).strip() for e in h2] != HEADINGS:
        errors.append("Expected exactly three H2 sections in the default order")
    positions = {text_of(e).strip(): i for i, e in enumerate(children) if e.tag == "h2"}
    intro = children[positions.get(HEADINGS[0], 0) + 1:positions.get(HEADINGS[1], 0)]
    insights = children[positions.get(HEADINGS[1], 0) + 1:positions.get(HEADINGS[2], 0)]
    body = children[positions.get(HEADINGS[2], len(children)) + 1:]
    callouts = root.findall(".//callout")
    if len(callouts) != 1 or not any(e is callouts[0] for e in insights):
        errors.append("Expected a single callout in the insights section")
    insight_count = 0
    if len(callouts) == 1:
        ordered = callouts[0].findall("ol")
        if len(ordered) != 1 or not ordered[0].findall("li"):
            errors.append("The callout must contain a nonempty ordered list")
        else:
            insight_count = len(ordered[0].findall("li"))
            if not 6 <= insight_count <= 9:
                warnings.append("The default suggests 6–9 insights; check whether the count fits")
    if root.findall(".//blockquote"):
        errors.append("Default layout does not use blockquotes")
    chapters = sum(e.tag == "h3" for e in body)
    if not 3 <= chapters <= 6 or len(root.findall(".//h3")) != chapters:
        errors.append("Expected 3–6 H3 chapters, all inside the transcript section")
    links = [a.get("href", "") for e in intro for a in e.iter("a")]
    valid_links = [link for link in links if urlparse(link).scheme in {"https", "http"} and urlparse(link).netloc]
    if not valid_links or (episode_url is not None and episode_url not in valid_links):
        errors.append("Intro lacks the required clickable episode link")
    counts = {"host": 0, "guest": 0}
    for number, paragraph in enumerate((e for e in body if e.tag == "p"), 1):
        text = text_of(paragraph).strip()
        if not text:
            continue
        label = re.split("[：:]", text, maxsplit=1)[0].strip()
        chunks = [(t, b, c) for t, b, c in styled_text(paragraph) if t.strip()]
        if label in hosts:
            counts["host"] += 1
            if not chunks or any(not b or c not in BLUE for _, b, c in chunks):
                errors.append(f"Paragraph {number}: host text must be entirely bold and blue")
        else:
            counts["guest"] += 1
            if guests and label not in guests:
                errors.append(f"Paragraph {number}: speaker label is absent from the supplied roster")
            if any(b or c not in BLACK for _, b, c in chunks):
                errors.append(f"Paragraph {number}: guest text must be plain black")
    if not counts["host"] or not counts["guest"]:
        errors.append("Expected both host and guest paragraphs; check labels/roster")
    full_text = text_of(root)
    if "\ufffd" in full_text:
        errors.append("Replacement character found: re-fetch safely before correcting the source")
    for phrase in ("ASR还原说明", "高亮来源说明", "时间戳未在源材料中标注"):
        if phrase in full_text:
            errors.append("Process notes found inside product text")
    return {"passed": not errors, "errors": errors, "warnings": warnings,
            "counts": {**counts, "chapters": chapters, "insights": insight_count},
            "scope": "layout only; source fidelity, coverage, timing and speaker truth require separate review"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--host", action="append", required=True, help="Exact displayed speaker label; repeatable")
    parser.add_argument("--guest", action="append", default=[], help="Optional complete guest roster; repeatable")
    parser.add_argument("--episode-url")
    args = parser.parse_args()
    results = []
    for path in args.files:
        try:
            result = check(content_of(path), set(args.host), set(args.guest), args.episode_url)
        except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as error:
            result = {"passed": False, "errors": [str(error)], "warnings": []}
        results.append({"file": str(path), **result})
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
