#!/usr/bin/env python3

from __future__ import annotations

import argparse
import email.utils
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_FEED_URL = "https://trumpstruth.org/feed"
DEFAULT_OUTPUT = Path("data/truth-corpus.jsonl")
DEFAULT_SNAPSHOT = Path("data/latest-truth-posts.json")
TRUTH_NS = {"truth": "https://truthsocial.com/ns"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Trump's Truth Social corpus from an accessible RSS archive."
    )
    parser.add_argument("--feed-url", default=DEFAULT_FEED_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--limit", type=int, default=50, help="Max items to keep in the snapshot output.")
    parser.add_argument("--timeout", type=int, default=20)
    return parser.parse_args()


def fetch_feed(feed_url: str, timeout: int) -> bytes:
    request = urllib.request.Request(
        feed_url,
        headers={
            "User-Agent": "trump-skill/1.0 (+https://truthsocial.com/@realDonaldTrump)"
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def html_to_text(value: str) -> str:
    text = re.sub(r"(?i)<br\\s*/?>", "\n", value)
    text = re.sub(r"(?i)</p>", "\n", text)
    text = re.sub(r"(?i)<p[^>]*>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_pub_date(value: str) -> str | None:
    if not value:
        return None
    dt = email.utils.parsedate_to_datetime(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def item_key(item: dict) -> str:
    return (
        item.get("truth_original_id")
        or item.get("guid")
        or item.get("archived_url")
        or item.get("truth_original_url")
        or item.get("title")
    )


def parse_feed(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("RSS feed missing channel node.")

    items: list[dict] = []
    fetched_at = datetime.now(timezone.utc).isoformat()

    for node in channel.findall("item"):
        title = (node.findtext("title") or "").strip()
        description_html = (node.findtext("description") or "").strip()
        archived_url = (node.findtext("link") or "").strip()
        guid = (node.findtext("guid") or "").strip()
        published_at = parse_pub_date((node.findtext("pubDate") or "").strip())
        truth_original_url = (
            node.findtext("truth:originalUrl", namespaces=TRUTH_NS) or ""
        ).strip()
        truth_original_id = (
            node.findtext("truth:originalId", namespaces=TRUTH_NS) or ""
        ).strip()

        items.append(
            {
                "source": "trumpstruth_rss",
                "title": title,
                "text": html_to_text(description_html),
                "description_html": description_html,
                "published_at": published_at,
                "archived_url": archived_url,
                "guid": guid,
                "truth_original_url": truth_original_url,
                "truth_original_id": truth_original_id,
                "fetched_at": fetched_at,
            }
        )

    return items


def load_existing(output_path: Path) -> dict[str, dict]:
    if not output_path.exists():
        return {}

    records: dict[str, dict] = {}
    with output_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            records[item_key(record)] = record
    return records


def sort_key(record: dict) -> tuple[str, str]:
    return (
        record.get("published_at") or "",
        record.get("truth_original_id") or record.get("guid") or "",
    )


def write_jsonl(output_path: Path, records: list[dict]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_snapshot(snapshot_path: Path, records: list[dict], limit: int) -> None:
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    latest = records[:limit]
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(latest),
        "items": latest,
    }
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()

    try:
        xml_bytes = fetch_feed(args.feed_url, args.timeout)
        fetched_items = parse_feed(xml_bytes)
    except Exception as exc:
        print(f"fetch failed: {exc}", file=sys.stderr)
        return 1

    existing = load_existing(args.output)
    before_count = len(existing)

    for item in fetched_items:
        existing[item_key(item)] = item

    records = sorted(existing.values(), key=sort_key, reverse=True)
    write_jsonl(args.output, records)
    write_snapshot(args.snapshot, records, args.limit)

    new_count = len(existing) - before_count
    print(
        json.dumps(
            {
                "feed_url": args.feed_url,
                "fetched": len(fetched_items),
                "new_records": new_count,
                "total_records": len(records),
                "output": str(args.output),
                "snapshot": str(args.snapshot),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
