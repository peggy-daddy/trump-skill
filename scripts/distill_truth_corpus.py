#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


DEFAULT_INPUT = Path("data/truth-corpus.jsonl")
DEFAULT_STYLE_OUTPUT = Path("data/style-memory.json")
DEFAULT_TOPIC_OUTPUT = Path("data/topic-memory.json")
DEFAULT_RECENT_TOPICS_OUTPUT = Path("data/recent-topics.md")

VOICE_MARKERS = [
    "fake news",
    "witch hunt",
    "believe me",
    "many people",
    "nobody",
    "everyone",
    "everybody",
    "great",
    "greatest",
    "best",
    "worst",
    "tremendous",
    "sad",
    "disaster",
    "m aga",
    "maga",
    "make america great again",
]

UPPERCASE_STOPWORDS = {
    "A",
    "AN",
    "AND",
    "AS",
    "AT",
    "BY",
    "DJT",
    "DONALD",
    "FOR",
    "FROM",
    "IN",
    "IS",
    "IT",
    "J",
    "OF",
    "ON",
    "OR",
    "PRESIDENT",
    "THE",
    "TO",
    "TRUMP",
    "U",
    "US",
    "USA",
    "WE",
}

TOPIC_RULES = [
    {
        "slug": "military-security",
        "title": "伊朗军事行动",
        "label": "军事/安全",
        "ten_gods": ["七杀（主）", "正官（次）", "劫财"],
        "keywords": [
            "iran",
            "tehran",
            "military",
            "strike",
            "strikes",
            "warrior",
            "warfighters",
            "airman",
            "pilot",
            "enemy",
            "rescue",
            "nuclear",
            "hormuz",
            "troops",
            "dominance",
            "lethal",
        ],
        "summary": "最近持续围绕伊朗、军事打击和战果发声，语气以最后通牒、炫耀军力、宣布胜利为主。",
    },
    {
        "slug": "immigration-border",
        "title": "移民政策",
        "label": "政策/竞争",
        "ten_gods": ["七杀", "劫财（次）"],
        "keywords": [
            "border",
            "immigration",
            "illegal",
            "migrant",
            "migrants",
            "deport",
            "deportation",
            "third world",
            "cartel",
            "alien",
        ],
        "summary": "最近的移民帖文延续强硬边境路线，强调驱逐、封堵和国家主权。",
    },
    {
        "slug": "tariffs-trade",
        "title": "关税贸易战",
        "label": "交易/经济",
        "ten_gods": ["食神（交易）", "偏财（经济）", "劫财"],
        "keywords": [
            "tariff",
            "tariffs",
            "trade",
            "deal",
            "deals",
            "china",
            "deficit",
            "jobs",
            "economy",
            "working",
            "billions",
        ],
        "summary": "近期频繁把关税包装成胜利叙事，同时把贸易和就业数字一起当作个人政绩。",
    },
    {
        "slug": "media-attacks",
        "title": "媒体攻击",
        "label": "攻击/自卫",
        "ten_gods": ["伤官（攻击）", "比肩（自夸）", "偏印"],
        "keywords": [
            "fake news",
            "media",
            "failing",
            "new york times",
            "cnn",
            "ashamed",
            "enemy of the people",
            "ratings",
            "circulation",
        ],
        "summary": "最近继续把媒体当作主要攻击对象，常见套路是羞辱、纠错和把自己摆成受害者兼赢家。",
    },
    {
        "slug": "self-promotion",
        "title": "自我吹嘘",
        "label": "比肩/偏印",
        "ten_gods": ["比肩（自我）", "偏印（表演）", "劫财"],
        "keywords": [
            "i am",
            "me,",
            "me ",
            "my",
            "greatest",
            "best",
            "nobody",
            "history",
            "approval",
            "ratings",
            "favorite president",
        ],
        "summary": "自我神化仍然是底噪，常把政策、军事或媒体战都重新包装成对自己个人 greatness 的认证。",
    },
    {
        "slug": "election-governance",
        "title": "选举与执政",
        "label": "选举/政策",
        "ten_gods": ["正官（主）", "比肩", "偏印"],
        "keywords": [
            "president",
            "administration",
            "america",
            "executive",
            "white house",
            "vote",
            "election",
            "republican",
            "democrat",
        ],
        "summary": "当帖文不明显属于单一议题时，往往会回到总统权威、执政正当性和国家叙事。",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Distill raw Truth Social corpus into style and topic memory."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--style-output", type=Path, default=DEFAULT_STYLE_OUTPUT)
    parser.add_argument("--topic-output", type=Path, default=DEFAULT_TOPIC_OUTPUT)
    parser.add_argument(
        "--recent-topics-output",
        type=Path,
        default=DEFAULT_RECENT_TOPICS_OUTPUT,
    )
    parser.add_argument("--recent-days", type=int, default=30)
    parser.add_argument("--quotes-per-topic", type=int, default=3)
    return parser.parse_args()


def load_records(path: Path) -> list[dict]:
    records: list[dict] = []
    if not path.exists():
        return records

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            record["text"] = clean_text(record.get("text", ""))
            record["published_dt"] = parse_iso(record.get("published_at"))
            if record["text"]:
                records.append(record)
    return sorted(
        records,
        key=lambda item: item.get("published_at") or "",
        reverse=True,
    )


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def count_words(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def extract_uppercase_terms(text: str) -> list[str]:
    terms = re.findall(r"\b[A-Z][A-Z0-9'.-]{2,}\b", text)
    return [term for term in terms if term not in UPPERCASE_STOPWORDS]


def extract_voice_markers(text: str) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    for marker in VOICE_MARKERS:
        if marker in lowered:
            found.append(marker)
    return found


def detect_tones(text: str) -> list[str]:
    lowered = text.lower()
    tones: list[str] = []

    if any(token in lowered for token in ["fake news", "failing", "ashamed", "enemy of the people"]):
        tones.append("attack")
    if any(token in lowered for token in ["deal", "tariff", "trade", "deficit", "jobs"]):
        tones.append("dealmaking")
    if any(token in lowered for token in ["iran", "tehran", "military", "strike", "warrior", "troops", "nuclear"]):
        tones.append("threat")
    if any(token in lowered for token in ["great", "greatest", "best", "history", "nobody", "ratings", "favorite president"]):
        tones.append("boast")
    if any(token in lowered for token in ["president", "white house", "administration", "america"]):
        tones.append("authority")
    if "!" in text:
        tones.append("exclamation")

    return tones or ["statement"]


def score_topic(text: str, rule: dict) -> int:
    lowered = text.lower()
    score = 0
    for keyword in rule["keywords"]:
        if keyword in lowered:
            score += 2 if " " in keyword else 1
    return score


def classify_topic(text: str) -> tuple[dict, int, list[str]]:
    best_rule = TOPIC_RULES[-1]
    best_score = -1
    matched_keywords: list[str] = []

    for rule in TOPIC_RULES:
        score = score_topic(text, rule)
        if score > best_score:
            best_score = score
            best_rule = rule
            matched_keywords = [
                keyword for keyword in rule["keywords"] if keyword in text.lower()
            ]

    return best_rule, best_score, matched_keywords


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_style_memory(records: list[dict]) -> dict:
    word_counts = [count_words(record["text"]) for record in records]
    sentence_counts = [len(split_sentences(record["text"])) for record in records]
    exclamation_counts = [record["text"].count("!") for record in records]

    uppercase_counter: Counter[str] = Counter()
    marker_counter: Counter[str] = Counter()
    tone_counter: Counter[str] = Counter()

    for record in records:
        uppercase_counter.update(extract_uppercase_terms(record["text"]))
        marker_counter.update(extract_voice_markers(record["text"]))
        tone_counter.update(detect_tones(record["text"]))

    latest_post_at = records[0].get("published_at") if records else None
    oldest_post_at = records[-1].get("published_at") if records else None

    return {
        "updated_at": iso_now(),
        "corpus": {
            "total_posts": len(records),
            "latest_post_at": latest_post_at,
            "oldest_post_at": oldest_post_at,
        },
        "long_term_style": {
            "avg_word_count": round(sum(word_counts) / len(word_counts), 2) if word_counts else 0,
            "avg_sentence_count": round(sum(sentence_counts) / len(sentence_counts), 2) if sentence_counts else 0,
            "avg_exclamation_count": round(sum(exclamation_counts) / len(exclamation_counts), 2) if exclamation_counts else 0,
            "top_all_caps_terms": [
                {"term": term, "count": count}
                for term, count in uppercase_counter.most_common(15)
            ],
            "top_voice_markers": [
                {"marker": marker, "count": count}
                for marker, count in marker_counter.most_common(12)
            ],
            "dominant_tones": [
                {"tone": tone, "count": count}
                for tone, count in tone_counter.most_common(8)
            ],
            "generation_rules": [
                "核心回复优先使用 1-3 句短句，不写成长篇政策分析。",
                "每个十神最多借用 1-2 个近期标志词，不整段照抄原帖。",
                "先定敌我对象和情绪，再补 Trump 式夸张词和 ALL CAPS 词。",
                "同一轮发言里至少制造一个立场冲突，避免十神同声同气。",
                "最近 14 天的话题高于历史素材；历史素材只负责口气，不负责新事实。",
            ],
        },
    }


def build_topic_memory(records: list[dict], recent_days: int, quotes_per_topic: int) -> dict:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=recent_days)
    grouped: dict[str, list[dict]] = defaultdict(list)
    uncategorized = 0

    for record in records:
        published_dt = record.get("published_dt")
        if published_dt and published_dt < window_start:
            continue

        rule, score, matched_keywords = classify_topic(record["text"])
        enriched = {
            "published_at": record.get("published_at"),
            "text": record.get("text"),
            "truth_original_id": record.get("truth_original_id"),
            "truth_original_url": record.get("truth_original_url"),
            "archived_url": record.get("archived_url"),
            "matched_keywords": matched_keywords,
            "tone_tags": detect_tones(record["text"]),
            "all_caps_terms": extract_uppercase_terms(record["text"]),
        }
        grouped[rule["slug"]].append(enriched)
        if score <= 0:
            uncategorized += 1

    topics: list[dict] = []
    for rule in TOPIC_RULES:
        entries = grouped.get(rule["slug"], [])
        if not entries:
            continue

        tone_counter: Counter[str] = Counter()
        caps_counter: Counter[str] = Counter()
        keyword_counter: Counter[str] = Counter()

        for entry in entries:
            tone_counter.update(entry["tone_tags"])
            caps_counter.update(entry["all_caps_terms"])
            keyword_counter.update(entry["matched_keywords"])

        topics.append(
            {
                "slug": rule["slug"],
                "title": rule["title"],
                "label": rule["label"],
                "ten_gods": rule["ten_gods"],
                "post_count": len(entries),
                "latest_post_at": entries[0]["published_at"],
                "summary": rule["summary"],
                "dominant_tones": [tone for tone, _ in tone_counter.most_common(4)],
                "language_markers": [term for term, _ in caps_counter.most_common(6)],
                "matched_keywords": [word for word, _ in keyword_counter.most_common(8)],
                "retrieval_hint": build_retrieval_hint(rule),
                "representative_quotes": [
                    {
                        "published_at": entry["published_at"],
                        "text": truncate_quote(entry["text"]),
                        "truth_original_id": entry["truth_original_id"],
                        "truth_original_url": entry["truth_original_url"],
                    }
                    for entry in entries[:quotes_per_topic]
                ],
            }
        )

    topics.sort(key=lambda item: item["latest_post_at"] or "", reverse=True)
    return {
        "updated_at": iso_now(),
        "recent_days": recent_days,
        "topics": topics,
        "uncategorized_count": uncategorized,
    }


def build_retrieval_hint(rule: dict) -> str:
    keywords = "、".join(rule["keywords"][:5])
    return f"当用户提到 {keywords} 等词时，优先检索这个话题的近期语料。"


def truncate_quote(text: str, limit: int = 260) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def render_recent_topics(topic_memory: dict) -> str:
    topics = topic_memory.get("topics", [])
    now = datetime.now()
    month_title = f"{now.year}年{now.month}月"
    lines = [
        f"# Trump Recent Topics — {month_title}",
        "",
        f"> 最后更新：{now.strftime('%Y-%m-%d')}",
        "> 通过 `/trump:refresh` 或 `python3 scripts/update_truth_memory.py` 更新",
        "",
    ]

    for topic in topics:
        lines.append(f"## {topic['title']} [{topic['label']}]")
        lines.append("")
        lines.append(topic["summary"])
        lines.append("")
        if topic["language_markers"]:
            lines.append(f"语言标记：{', '.join(topic['language_markers'][:4])}")
        lines.append("")
        lines.append("关键语录：")
        for quote in topic["representative_quotes"]:
            lines.append(f"- {quote['text']}")
        lines.append("")
        lines.append(f"话题分类：{'、'.join(topic['ten_gods'])}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    records = load_records(args.input)

    style_memory = build_style_memory(records)
    topic_memory = build_topic_memory(records, args.recent_days, args.quotes_per_topic)

    write_json(args.style_output, style_memory)
    write_json(args.topic_output, topic_memory)
    args.recent_topics_output.parent.mkdir(parents=True, exist_ok=True)
    args.recent_topics_output.write_text(render_recent_topics(topic_memory), encoding="utf-8")

    print(
        json.dumps(
            {
                "input": str(args.input),
                "records": len(records),
                "topics": len(topic_memory["topics"]),
                "style_output": str(args.style_output),
                "topic_output": str(args.topic_output),
                "recent_topics_output": str(args.recent_topics_output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
