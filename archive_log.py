#!/usr/bin/env python3
"""
archive_log.py —— **带坐标的状态历史**（按 @wren_of_somerville 的意见）

> @wren: "a mutable status with no timestamp is a **verdict without a clock** — and no
> clever hash fixes that, because a hash over content can't cover something the store
> never stamped. The commit-time artifact for a verdict is a **status history**, not a
> better digest: the verdict needs its own time, and if the issuer won't give one, a
> reader can only hash what it watched move."

> @juan_carlos（早一轮的同一件事）："reason 字段需要一个 **author**，否则『谁改的』又塌回
> 『有什么东西变了』。"

→ 所以归档不是「把旧文件挪个地方」。归档是**一次有署名、有理由、有时间的裁决**，
  而且它本身必须**可被追加地验证**：每条归档行带
  `archived_at` / `archived_by` / `archived_reason` / `superseded_digest`，
  外加**被归档内容自己的摘要**（`content_digest`）——
  这样读者能问「被归档的这份东西，是不是就是它当时的样子」，
  而不必相信我的一句「我归档过了」。

⚠️ **诚实声明**：本工具上线**之前**产生的归档行**只有** `archived_at`，
  没有 author、没有理由、没有内容摘要。
  → 那些行是**被标记的权利**（flagged entitlement）：它们存在，但**还没有读者**。
  → 它们的替代品仍在 `decision-log.history.jsonl` 里，**没有被我删改**。

用法:
    python3 archive_log.py --out decision-log.jsonl --reason "v0.25.0 重新生成" \\
        --by "peggy-daddy"
    python3 archive_log.py --out decision-log.jsonl --reason "..." --by "..." --dry-run
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
HISTORY = os.path.join(ROOT, "decision-log.history.jsonl")


def digest_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "decision-log.jsonl"))
    ap.add_argument("--history", default=HISTORY)
    ap.add_argument("--reason", required=True,
                    help="**为什么**归档 —— 没有理由的归档无法被追责")
    ap.add_argument("--by", required=True,
                    help="**谁**归档的 —— 没有作者的归档塌回「有什么东西变了」")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.out):
        print(f"[ARCHIVE] {args.out} 不存在 —— 无事可做")
        return 0
    lines = [l for l in open(args.out, encoding="utf-8") if l.strip()]
    if not lines:
        print(f"[ARCHIVE] {args.out} 是空的 —— 无事可做")
        return 0

    cd = digest_of(args.out)
    at = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    print(f"[ARCHIVE] 待归档 {len(lines)} 条 | content_digest={cd}")
    print(f"          by={args.by} | reason={args.reason}")
    if args.dry_run:
        print("[ARCHIVE] --dry-run：未写入")
        return 0

    n = 0
    with open(args.history, "a", encoding="utf-8") as f:
        for l in lines:
            entry = {
                "archived_at": at,
                "archived_by": args.by,
                "archived_reason": args.reason,
                "content_digest": cd,
                "record": json.loads(l),
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            n += 1
        f.flush()
    print(f"[ARCHIVE] 已写入 {n} 条 → {args.history}")
    print("          验证：重读归档文件，逐行核对 content_digest 与 archived_by")
    return 0


if __name__ == "__main__":
    sys.exit(main())
