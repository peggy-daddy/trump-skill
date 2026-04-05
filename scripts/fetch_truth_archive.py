#!/usr/bin/env python3

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_ARCHIVE_URL = "https://ix.cnn.io/data/truth-social/truth_archive.json"
DEFAULT_OUTPUT = Path("data/truth-corpus.jsonl")
DEFAULT_SNAPSHOT = Path("data/latest-truth-posts.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Trump's Truth archive from the live CNN JSON feed."
    )
    parser.add_argument("--archive-url", default=DEFAULT_ARCHIVE_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--timeout", type=int, default=30)
    return parser.parse_args()


def fetch_archive(archive_url: str, timeout: int) -> list[dict]:
    request = urllib.request.Request(
        archive_url,
        headers={
            "User-Agent": "trump-skill/1.0 (+https://truthsocial.com/@realDonaldTrump)"
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError("Archive response is not a JSON list.")
    return payload


def clean_text(value: str) -> str:
    text = re.sub(r"(?i)<br\\s*/?>", "\n", value)
    text = re.sub(r"(?i)</p>", "\n", text)
    text = re.sub(r"(?i)<p[^>]*>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def build_title(text: str, fallback: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return fallback
    if len(compact) <= 140:
        return compact
    return compact[:137].rstrip() + "..."


def item_key(item: dict) -> str:
    return (
        item.get("truth_original_id")
        or item.get("guid")
        or item.get("truth_original_url")
        or item.get("archived_url")
        or item.get("title")
    )


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
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": min(limit, len(records)),
        "items": records[:limit],
    }
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def normalize_items(items: list[dict]) -> list[dict]:
    fetched_at = datetime.now(timezone.utc).isoformat()
    normalized: list[dict] = []

    for item in items:
        text = clean_text(item.get("content", ""))
        truth_original_id = str(item.get("id", "")).strip()
        truth_original_url = (item.get("url") or "").strip()
        published_at = (item.get("created_at") or "").strip()
        media = item.get("media") or []

        normalized.append(
            {
                "source": "cnn_truth_archive",
                "title": build_title(text, f"[No Title] - Post {truth_original_id}"),
                "text": text,
                "description_html": item.get("content", ""),
                "published_at": published_at,
                "archived_url": truth_original_url,
                "guid": truth_original_id,
                "truth_original_url": truth_original_url,
                "truth_original_id": truth_original_id,
                "media": media,
                "replies_count": item.get("replies_count"),
                "reblogs_count": item.get("reblogs_count"),
                "favourites_count": item.get("favourites_count"),
                "fetched_at": fetched_at,
            }
        )

    return normalized


def main() -> int:
    args = parse_args()

    try:
        fetched_items = normalize_items(fetch_archive(args.archive_url, args.timeout))
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

    print(
        json.dumps(
            {
                "archive_url": args.archive_url,
                "fetched": len(fetched_items),
                "new_records": len(existing) - before_count,
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
