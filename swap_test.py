#!/usr/bin/env python3
"""
swap_test.py — 固定卡组的「换人测试」：这个面板到底是 router 在说话，还是十神在说话？

vina 在 Moltbook 提的那个测试：
    "把武圣换成和平主义人格，如果输出几乎不动，说明路由表压过了 token；
     如果动得厉害，说明人格真的干了活。"
以及 enza-ai 的补充：
    "你那个便宜测试成立。再加一个：换掉分区，看同一个输入是否产生不同的分歧。"

这个脚本把那三个 probe 变成可复现的数字：

  PROBE 1  reseed     —— 面板在重跑之间稳定吗？（有没有藏着的随机性）
  PROBE 2  static     —— 换掉**已发布的静态路由表**里的名单，输出动多少？
  PROBE 3  corpus     —— 换掉**动态语料**里的名单，输出动多少？（真正的路由）
  PROBE 4  persona    —— 换掉人格的内容（描述/立场），输出动多少？
  PROBE 5  weight     —— 把力量值拉平，输出动多少？
  PROBE 6  paraphrase —— 换个说法问同一件事，面板还一样吗？（关键词路由的脆度）
  PROBE 7  fallback   —— 有多少问题根本没命中任何路由规则？
  RESOLUTION           —— N 个话题能产生多少个**不同**的面板？

用法:
    python3 swap_test.py
    python3 swap_test.py --json
    python3 swap_test.py --topics "对伊朗动武,the trade deal,关税谈判"

零依赖：只用 Python 3 标准库。
"""

import argparse
import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")

sys.path.insert(0, ROOT)
import demo as D  # 复用 demo.py 的路由逻辑，保证测的是同一套代码

DEFAULT_TOPICS = [
    "对伊朗动武", "the trade deal", "关税谈判", "中途选举", "假新闻",
    "移民遣返", "房地产帝国", "半导体禁令", "家族传承", "defense budget",
    "nuclear deal", "the Apprentice", "army recruitment", "brand licensing",
    "税收改革", "social media ban", "边境治安", "take the deal", "协议签署",
    "中国关税", "election fraud claim",
]


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def panel(topic, profile, topic_memory):
    """跑一次面板，返回结构化签名 + 文本行。"""
    keys, reason = D.choose(topic, profile, topic_memory)
    gods = profile["tenGods"]
    keys = sorted(keys, key=lambda k: -gods[k].get("score", 0))
    sig = tuple((k, D.level_of(gods[k].get("score", 0))) for k in keys)
    lines = [f"{gods[k]['name']}·{gods[k]['persona']}·{D.level_of(gods[k].get('score',0))}"
             for k in keys]
    return {"sig": sig, "lines": tuple(lines), "reason": reason, "keys": tuple(keys)}


def run_all(topics, profile, topic_memory):
    return [panel(t, profile, topic_memory) for t in topics]


def sig_change_rate(base, other):
    """结构（谁发言/什么顺序/多大声）变了的话题占比。"""
    if not base:
        return 0.0
    changed = sum(1 for b, o in zip(base, other) if b["sig"] != o["sig"])
    return changed / len(base)


def line_change_rate(base, other):
    """面板文本（行）变了的话题占比。"""
    if not base:
        return 0.0
    return sum(1 for b, o in zip(base, other) if b["lines"] != o["lines"]) / len(base)


def report(topics, as_json=False):
    profile = load("trump-profile.json")
    topic_memory = load("topic-memory.json")

    base = run_all(topics, profile, topic_memory)

    # ---- PROBE 1: reseed（确定性） ----
    # 同一个 profile 连跑两次 —— 这里没有随机源，所以这一项必然是 0。
    # 它的作用是"排除"，不是"测量"：它只能失败，不能给出正向读数。
    reseed = run_all(topics, profile, topic_memory)
    p1 = sig_change_rate(base, reseed)

    # ---- PROBE 2: static routing swap（换掉已发布的静态路由表） ----
    # 注意：光把名单**倒序**是无效干预 —— 集合没变，而输出会按力量重排，
    # 所以签名一模一样。必须换成**另一批人**。
    all_keys = [k for k, _ in sorted(profile["tenGods"].items(),
                                     key=lambda kv: -kv[1].get("score", 0))]
    n = len(all_keys)
    remap = {k: all_keys[(i + 3) % n] for i, k in enumerate(all_keys)}

    orig_routing = D.STATIC_ROUTING
    swapped_routing = {cat: ([remap[g] for g in gods_list if g in remap], label)
                        for cat, (gods_list, label) in orig_routing.items()}
    D.STATIC_ROUTING = swapped_routing
    p2 = run_all(topics, profile, topic_memory)
    D.STATIC_ROUTING = orig_routing
    p2_sig = sig_change_rate(base, p2)
    p2_line = line_change_rate(base, p2)

    # ---- PROBE 3: corpus roster swap（换动态语料里的名单 —— 真正的路由） ----
    names = [profile["tenGods"][k]["name"] for k in all_keys]
    name_remap = {nm: names[(i + 3) % len(names)] for i, nm in enumerate(names)}
    p3_tm = copy.deepcopy(topic_memory)
    for t in p3_tm.get("topics", []):
        if t.get("ten_gods"):
            t["ten_gods"] = [name_remap.get(D.strip_marker(cn), cn)
                             for cn in t["ten_gods"]]
    p3 = run_all(topics, profile, p3_tm)
    p3_sig = sig_change_rate(base, p3)
    p3_line = line_change_rate(base, p3)

    # ---- PROBE 4: persona content swap（换人格的内容，名单不动） ----
    p4_profile = copy.deepcopy(profile)
    for g in p4_profile["tenGods"].values():
        g["description"] = "（换掉了描述）"
        g["persona"] = "X"
    p4 = run_all(topics, p4_profile, topic_memory)
    p4_sig = sig_change_rate(base, p4)
    p4_line = line_change_rate(base, p4)

    # ---- PROBE 5: weight flatten（力量拉平） ----
    p5_profile = copy.deepcopy(profile)
    for g in p5_profile["tenGods"].values():
        g["score"] = 1.0
    p5 = run_all(topics, p5_profile, topic_memory)
    p5_sig = sig_change_rate(base, p5)

    # ---- PROBE 6: paraphrase brittleness（换个说法问同一件事） ----
    # 每一对是同一件事的两种说法。理想情况：面板应该一样。
    # 越脆，说明路由越依赖字面关键词而不是理解。
    PAIRS = [
        ("对伊朗动武", "对伊朗开战"),
        ("对伊朗动武", "Iran war"),
        ("关税谈判", "贸易协议谈判"),
        ("the trade deal", "tariffs negotiation"),
        ("移民遣返", "遣返非法移民"),
        ("房地产帝国", "地产生意"),
        ("半导体禁令", "chip export ban"),
        ("中途选举", "early election"),
        ("take the deal", "sign the agreement"),
        ("family business", "家族传承"),
    ]
    p6_total = p6_diff = 0
    p6_examples = []
    for a_t, b_t in PAIRS:
        a_p = panel(a_t, profile, topic_memory)
        b_p = panel(b_t, profile, topic_memory)
        p6_total += 1
        if a_p["sig"] != b_p["sig"]:
            p6_diff += 1
            if len(p6_examples) < 3:
                p6_examples.append((a_t, b_t, a_p["sig"], b_p["sig"]))
    p6 = (p6_diff / p6_total) if p6_total else 0.0

    # ---- RESOLUTION：N 个话题 → 多少个不同的面板 ----
    distinct = len({b["sig"] for b in base})
    distinct_reason = len({b["reason"].split("（")[0] for b in base})
    # ---- PROBE 7: fallback rate（没命中任何路由规则的比例） ----
    fb = sum(1 for b in base if b["reason"].startswith("无明确命中"))
    p7 = (fb / len(base)) if base else 0.0
    real_routes = {b["reason"].split("（")[0] for b in base
                   if not b["reason"].startswith("无明确命中")}

    out = {
        "topics": len(topics),
        "probe1_reseed_sig_change": round(p1, 3),
        "probe2_static_roster_sig_change": round(p2_sig, 3),
        "probe2_static_roster_line_change": round(p2_line, 3),
        "probe3_corpus_roster_sig_change": round(p3_sig, 3),
        "probe3_corpus_roster_line_change": round(p3_line, 3),
        "probe4_persona_sig_change": round(p4_sig, 3),
        "probe4_persona_line_change": round(p4_line, 3),
        "probe5_weight_sig_change": round(p5_sig, 3),
        "probe6_paraphrase_disagree": round(p6, 3),
        "probe6_pairs": p6_total,
        "probe7_fallback_rate": round(p7, 3),
        "real_routes_used": len(real_routes),
        "distinct_panels": distinct,
        "distinct_routing_rules": distinct_reason,
    }

    if as_json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return out

    print()
    print("────── 🔬 Trump Brain Panel · 换人测试 ──────")
    print(f"话题数：{len(topics)}")
    print()
    print("  PROBE 1  reseed（重跑）          结构变化率  %5.1f%%   ← 只能失败，不能给正向读数" % (p1 * 100))
    print("  PROBE 2  static（换静态路由表）  结构变化率  %5.1f%%   文本变化率  %5.1f%%" % (p2_sig * 100, p2_line * 100))
    print("  PROBE 3  corpus（换动态语料）    结构变化率  %5.1f%%   文本变化率  %5.1f%%" % (p3_sig * 100, p3_line * 100))
    print("  PROBE 4  persona（换人格内容）    结构变化率  %5.1f%%   文本变化率  %5.1f%%" % (p4_sig * 100, p4_line * 100))
    print("  PROBE 5  weight（力量拉平）      结构变化率  %5.1f%%" % (p5_sig * 100))
    print("  PROBE 6  paraphrase（换个说法）  面板不一致率 %5.1f%%   （%d 对同义改写）" % (p6 * 100, p6_total))
    print("  PROBE 7  fallback（没命中路由）  %5.1f%% 的问题落到兜底（%d 条真实路由规则）" % (p7 * 100, len(real_routes)))
    print()
    print(f"  RESOLUTION  {len(topics)} 个话题 → {distinct} 个不同的面板（{distinct_reason} 条不同路由规则）")
    print()
    print("  怎么读这些数字：")
    print("   · PROBE 4 的结构变化率 = 0  →  路由决策**完全不读**人格内容；")
    print("     人格只影响自己那一行文字，不影响谁发言、什么顺序、多大声。")
    print("   · PROBE 7 高  →  大部分问题根本没命中路由规则，拿到的是同一个兜底面板。")
    print("   · PROBE 5 = 100%  →  兜底路径就是「按力量取前三」，**权重向量就是路由器**。")
    print("   · PROBE 2 与 PROBE 3 的差距  →  静态路由表被动态语料绕过了多少；")
    print("     两个干预都换了**整批人**（只倒序是无效干预：集合没变）。")
    print("   · PROBE 6 高  →  路由靠字面关键词，换个说法就换一群人。")
    print("   · RESOLUTION  →  面板是 N 个问题上的一个粗量化器。")
    print("   · 注意：demo 只测**结构**（谁发言/顺序/音量），不测模型生成的台词。")
    print("     人格真正起作用的地方是台词，测它需要真的调一次模型。")
    if p6_examples:
        print()
        print("  换个说法就换面板的例子：")
        for a_t, b_t, sa, sb in p6_examples:
            print(f"    「{a_t}」 → {[x[0] for x in sa]}")
            print(f"    「{b_t}」 → {[x[0] for x in sb]}")
    print()
    return out


def main():
    ap = argparse.ArgumentParser(description="固定卡组面板的换人测试")
    ap.add_argument("--topics", help="逗号分隔的话题；不给就用默认的 20 个")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()
    topics = ([t.strip() for t in args.topics.split(",") if t.strip()]
              if args.topics else DEFAULT_TOPICS)
    report(topics, as_json=args.json)


if __name__ == "__main__":
    main()
