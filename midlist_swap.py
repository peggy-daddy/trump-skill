#!/usr/bin/env python3
"""
midlist_swap.py —— **中位互换探针**（按 @vina 在 173a236f 下的建议实现）

@vina: "Since the speaker sequence shifts whenever a top-tier persona is removed,
the hierarchy is clearly structurally significant. To determine if this order is
**baked into the routing logic itself** or if it's just a side effect of how your
persona removal method re-indexes the list, try a **'mid-list swap.'**
Instead of removing a persona, **swap the first-named persona with the third-named
persona in one category.** If the sequence remains identical except for that one swap,
the order is a direct property of the table."

→ 这是一个**我之前没做的对照**：我的 PROBE 测的都是「**移除**」，
  而移除会**重新编号** → 任何「按名册分数重算顺序」的实现都会跟着动。
  → 所以「移除会改顺序」这个观察，**分不清**「顺序来自表」和「顺序来自重算」。
  → 互换是**不改变集合、只改变位置**的操作：集合不变 → 不会触发重算逻辑的差异，
     如果输出**只有那一处对调**，就说明顺序是**表的直接属性**。

用法:
    python3 midlist_swap.py            # 退出码 0 = 全部类别符合预期
    python3 midlist_swap.py --json
"""
import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import demo as D  # noqa: E402

PROFILE = json.load(open(os.path.join(ROOT, "data", "trump-profile.json"), encoding="utf-8"))
TM = json.load(open(os.path.join(ROOT, "data", "topic-memory.json"), encoding="utf-8"))

# 每个类别挑一个能命中它的主题
# 每个类别挑一个**能命中它**的主题。
# 注意：不能只测 2 个类别 —— 「只对调那一处」这个结论的强度取决于覆盖面。
TOPIC_FOR = {
    "military": "military airman",
    "deal": "tariff negotiat",
    "media": "fake news 假新闻",
    "ego": "me 我",
    "rival": "illegal enemy",
    "family": "family fred",
    "money": "real estate property",
    "policy": "president bill",
    "tech": "tiktok ai",
}


def route_for(topic, table):
    """在**给定**的表上跑一次选人（不改动全局）。"""
    old = D.STATIC_ROUTING
    D.STATIC_ROUTING = table
    try:
        _k, _src = D.choose(topic, PROFILE, TM)
        return _k, _src
    finally:
        D.STATIC_ROUTING = old


def main():
    as_json = "--json" in sys.argv
    rows = []
    for cat, (gods, label) in D.STATIC_ROUTING.items():
        if len(gods) < 3:
            rows.append({"category": cat, "skip": "该类别不足 3 人，无法互换第 1 与第 3 位"})
            continue
        topic = TOPIC_FOR.get(cat)
        if not topic:
            rows.append({"category": cat, "skip": "没有可命中的主题"})
            continue
        base_tbl = copy.deepcopy(D.STATIC_ROUTING)
        base, base_src = route_for(topic, base_tbl)
        if "静态路由表" not in base_src:
            rows.append({"category": cat, "skip":
                         "该主题**没有命中静态表**（走到 %s）—— 测兜底路径没有意义"
                         % base_src.split("→")[0].strip()})
            continue

        # 互换第 1 与第 3 位（**不改变集合**）
        swap_tbl = copy.deepcopy(D.STATIC_ROUTING)
        g = list(swap_tbl[cat][0])
        g[0], g[2] = g[2], g[0]
        swap_tbl[cat] = (g, swap_tbl[cat][1])
        got, got_src = route_for(topic, swap_tbl)

        # 期望：基线序列**只有**第 1 与第 3 位对调
        exp = list(base)
        if len(exp) >= 3:
            exp[0], exp[2] = exp[2], exp[0]
        ok = (got == exp)
        rows.append({
            "category": cat, "label": label, "topic": topic,
            "baseline": base, "swapped": got, "expected": exp,
            "ok": ok,
            "verdict": ("顺序是**表的直接属性**（只对调了那一处）" if ok
                        else "顺序**不是**表的直接属性 —— 另有重算/重排逻辑在动"),
        })

    tested = [r for r in rows if "ok" in r]
    passed = sum(1 for r in tested if r["ok"])
    if as_json:
        print(json.dumps({"tested": len(tested), "passed": passed, "rows": rows},
                         ensure_ascii=False, indent=2))
    else:
        for r in rows:
            if "skip" in r:
                print(f"  --   {r['category']:<10} 跳过：{r['skip']}")
                continue
            mark = "OK " if r["ok"] else "FAIL"
            print(f"  {mark}  {r['category']:<10} base={r['baseline']}")
            print(f"       swapped={r['swapped']}")
            if not r["ok"]:
                print(f"       expected={r['expected']}")
    print(f"\n[PROBE mid-list-swap] {passed}/{len(tested)} 个类别的顺序是表的直接属性")
    if tested and passed == len(tested):
        print("  → 结论：互换第 1/第 3 位，输出**只**对调那一处，"
              "其余完全不变 → 顺序由表决定，**不是**移除后重算的副作用。")
    return 0 if (tested and passed == len(tested)) else 1


if __name__ == "__main__":
    sys.exit(main())
