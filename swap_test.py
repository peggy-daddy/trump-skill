#!/usr/bin/env python3
"""
swap_test.py — 固定卡组的「换人测试」：这个面板到底是 router 在说话，还是十神在说话？

vina 在 Moltbook 提的那个测试：
    "把武圣换成和平主义人格，如果输出几乎不动，说明路由表压过了 token；
     如果动得厉害，说明人格真的干了活。"
以及 enza-ai 的补充：
    "你那个便宜测试成立。再加一个：换掉分区，看同一个输入是否产生不同的分歧。"

这个脚本把那三个 probe 变成可复现的数字：

  PROBE 1  reseed       —— 面板在重跑之间稳定吗？（有没有藏着的随机性）
  PROBE 2  static       —— 换掉**已发布的静态路由表**里的名单，输出动多少？
  PROBE 3  corpus       —— 换掉**动态语料**里的名单，输出动多少？（真正的路由）
  PROBE 4  profile desc —— 换掉 trump-profile.json 里的描述字段，输出动多少？
  PROBE 5  weight       —— 把力量值拉平，输出动多少？
  PROBE 6  paraphrase   —— 换个说法问同一件事，面板还一样吗？
  PROBE 7  fallback     —— 有多少问题根本没命中任何路由规则？
  PROBE 8  persona layer—— 把 10 个 persona SKILL.md 全部中性化，结构变不变？
  PROBE 9  table parity —— demo.py 里手抄的路由表 == skills/ask/SKILL.md 里的真表吗？
  RESOLUTION             —— N 个话题能产生多少个**不同**的面板？

⚠️ 这个脚本只能看到**结构层**（谁发言/顺序/音量）。
它看不到人格层（skills/<十神>/SKILL.md 里的人格内容），因为那层只在**模型生成台词**时才被加载。
PROBE 8 就是把这个盲区**当成一个数字报出来**，而不是藏在脚注里。

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
import re
import shutil
import sys
import tempfile

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
    return sum(1 for b, o in zip(base, other) if b["sig"] != o["sig"]) / len(base)


def line_change_rate(base, other):
    """面板文本（行）变了的话题占比。"""
    if not base:
        return 0.0
    return sum(1 for b, o in zip(base, other) if b["lines"] != o["lines"]) / len(base)


def _remap_gods(profile):
    """把每个人换成一个**不同的人**（不是倒序 —— 倒序是无效干预）。"""
    all_keys = [k for k, _ in sorted(profile["tenGods"].items(),
                                     key=lambda kv: -kv[1].get("score", 0))]
    n = len(all_keys)
    return {k: all_keys[(i + 3) % n] for i, k in enumerate(all_keys)}


def report(topics, as_json=False):
    profile = load("trump-profile.json")
    topic_memory = load("topic-memory.json")

    base = run_all(topics, profile, topic_memory)

    # ---- PROBE 1: reseed（确定性） ----
    # 这个面板没有随机源，所以这一项必然是 0。
    # 它的作用是"排除"，不是"测量"：它只能失败，不能给出正向读数。
    reseed = run_all(topics, profile, topic_memory)
    p1 = sig_change_rate(base, reseed)

    # ---- PROBE 2: static routing swap（换掉已发布的静态路由表） ----
    remap = _remap_gods(profile)
    orig_routing = D.STATIC_ROUTING
    D.STATIC_ROUTING = {cat: ([remap[g] for g in gl if g in remap], label)
                        for cat, (gl, label) in orig_routing.items()}
    p2 = run_all(topics, profile, topic_memory)
    D.STATIC_ROUTING = orig_routing
    p2_sig = sig_change_rate(base, p2)
    p2_line = line_change_rate(base, p2)

    # ---- PROBE 3: corpus roster swap（换动态语料里的名单 —— 真正的路由） ----
    all_keys = list(remap.keys())
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

    # ---- PROBE 4: profile description swap（换 trump-profile.json 的描述字段） ----
    # ⚠️ 准确的说法：这是 **profile.json 的 description 字段**，不是人格内容。
    # 人格内容在 skills/<十神>/SKILL.md 里（PROBE 8 单独处理）。
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

    # ---- PROBE 7: fallback rate（没命中任何路由规则的比例） ----
    fb = sum(1 for b in base if b["reason"].startswith("无明确命中"))
    p7 = (fb / len(base)) if base else 0.0
    real_routes = {b["reason"].split("（")[0] for b in base
                   if not b["reason"].startswith("无明确命中")}

    # ---- PROBE 8: persona layer perturbation（中性化 10 个 persona SKILL.md） ----
    # 人格内容在 skills/<key>/SKILL.md。这个探针**真的把文件改了**（写到临时目录），
    # 然后重跑面板。结构不会变 —— 因为 demo 从来不读那些文件。
    # **这个 0% 测的是探针自己的盲区，不是 artifact 的人格层。**
    p8_changed = 0
    p8_sig = 0.0
    persona_dir = os.path.join(ROOT, "skills")
    if os.path.isdir(persona_dir):
        with tempfile.TemporaryDirectory() as td:
            shutil.copytree(persona_dir, os.path.join(td, "skills"))
            for dp, dn, fn in os.walk(os.path.join(td, "skills")):
                for f in fn:
                    if f == "SKILL.md":
                        fp = os.path.join(dp, f)
                        open(fp, "w", encoding="utf-8").write(
                            "---\nname: neutralized\ndescription: neutralized\n---\n\n# neutralized\n")
                        p8_changed += 1
            p8 = run_all(topics, profile, topic_memory)
            p8_sig = sig_change_rate(base, p8)
    # 其中有多少是「十神人格」目录下的（其余是 ask/correct/daily 等命令）
    PERSONA_KEYS = {k for k, _ in profile["tenGods"].items()}
    p8_persona = 0
    for k in PERSONA_KEYS:
        if os.path.exists(os.path.join(ROOT, "skills", k, "SKILL.md")):
            p8_persona += 1

    # ---- PROBE 9: routing table parity（demo 的手抄表 vs ask/SKILL.md 的真表） ----
    # demo.py 把路由表**手抄**了一份在 Python 里。两份可能漂移，且没人会发现。
    ask_md = os.path.join(ROOT, "skills", "ask", "SKILL.md")
    parity_diff = None
    parity_missing = []
    if os.path.exists(ask_md):
        md = open(ask_md, encoding="utf-8").read()
        md_map = {}
        for line in md.splitlines():
            m = re.match(r"^\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$", line)
            if not m:
                continue
            label, gods_cell = m.group(1), m.group(2)
            names = re.findall(r"[\u4e00-\u9fff]+", gods_cell)
            if len(names) != 3:
                continue
            keys = []
            for nm in names:
                k = D.name_to_key(profile, nm)
                if k:
                    keys.append(k)
            if len(keys) == 3:
                md_map[label] = tuple(keys)
        py_map = {label: tuple(gl) for gl, label in D.STATIC_ROUTING.values()}
        common = set(md_map) & set(py_map)
        parity_diff = [(lbl, md_map[lbl], py_map[lbl])
                       for lbl in sorted(common) if md_map[lbl] != py_map[lbl]]
        parity_missing = sorted(set(md_map) ^ set(py_map))

    # ---- RESOLUTION：N 个话题 → 多少个不同的面板 ----
    distinct = len({b["sig"] for b in base})
    distinct_reason = len({b["reason"].split("（")[0] for b in base})

    out = {
        "topics": len(topics),
        "probe1_reseed_sig_change": round(p1, 3),
        "probe2_static_roster_sig_change": round(p2_sig, 3),
        "probe2_static_roster_line_change": round(p2_line, 3),
        "probe3_corpus_roster_sig_change": round(p3_sig, 3),
        "probe3_corpus_roster_line_change": round(p3_line, 3),
        "probe4_profile_desc_sig_change": round(p4_sig, 3),
        "probe4_profile_desc_line_change": round(p4_line, 3),
        "probe5_weight_sig_change": round(p5_sig, 3),
        "probe6_paraphrase_disagree": round(p6, 3),
        "probe6_pairs": p6_total,
        "probe7_fallback_rate": round(p7, 3),
        "real_routes_used": len(real_routes),
        "probe8_persona_layer_files_neutralized": p8_changed,
        "probe8_persona_layer_persona_files": p8_persona,
        "probe8_persona_layer_sig_change": round(p8_sig, 3),
        "probe9_table_parity_mismatches": (len(parity_diff) if parity_diff is not None else None),
        "probe9_table_parity_missing": (parity_missing if parity_diff is not None else None),
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
    print("  PROBE 1  reseed（重跑）            结构变化率  %5.1f%%   ← 只能失败，不能给正向读数" % (p1 * 100))
    print("  PROBE 2  static（换静态路由表）    结构变化率  %5.1f%%   文本变化率  %5.1f%%" % (p2_sig * 100, p2_line * 100))
    print("  PROBE 3  corpus（换动态语料）      结构变化率  %5.1f%%   文本变化率  %5.1f%%" % (p3_sig * 100, p3_line * 100))
    print("  PROBE 4  profile描述（换描述字段）  结构变化率  %5.1f%%   文本变化率  %5.1f%%" % (p4_sig * 100, p4_line * 100))
    print("  PROBE 5  weight（力量拉平）        结构变化率  %5.1f%%" % (p5_sig * 100))
    print("  PROBE 6  paraphrase（换个说法）    面板不一致率 %5.1f%%   （%d 对同义改写）" % (p6 * 100, p6_total))
    print("  PROBE 7  fallback（没命中路由）    %5.1f%% 的问题落到兜底（%d 条真实路由规则）" % (p7 * 100, len(real_routes)))
    print("  PROBE 8  persona layer（中性化）   结构变化率  %5.1f%%   （改了 %d 个 SKILL.md，其中 %d 个是十神人格）" % (p8_sig * 100, p8_changed, p8_persona))
    if parity_diff is None:
        print("  PROBE 9  table parity             跳过（找不到 skills/ask/SKILL.md）")
    else:
        print("  PROBE 9  table parity             %s" % ("✅ 两份路由表一致" if not parity_diff else "❌ %d 条不一致: %s" % (len(parity_diff), parity_diff)))
        if parity_missing:
            print("                               仅出现在一份表里的条目: %s" % parity_missing)
    print()
    print(f"  RESOLUTION  {len(topics)} 个话题 → {distinct} 个不同的面板（{distinct_reason} 条不同路由规则）")
    print()
    print("  怎么读这些数字：")
    print("   · PROBE 4 = 0%  →  **trump-profile.json 的 description 字段**不影响路由。")
    print("     注意：这是 profile 的描述，不是人格内容。")
    print("   · PROBE 8 = 0%%  →  把 %d 个 persona SKILL.md 全部中性化，结构**完全不变**。" % p8_changed)
    print("     **这 0% 测的是探针自己的盲区，不是 artifact 的人格层** —— demo 从不加载那些文件。")
    print("     人格层只在模型生成台词时进入，所以人格的影响**必须调一次模型才能测**。")
    print("   · PROBE 7 高  →  大部分问题根本没命中路由规则，拿到的是同一个兜底面板。")
    print("   · PROBE 5 = 100%  →  兜底路径就是「按力量取前三」，**权重向量就是路由器**。")
    print("   · PROBE 9  →  demo.py 里手抄了一份路由表；今天两份一致，但没有东西保证明天还一致。")
    print("   · PROBE 6 高  →  路由靠字面关键词，换个说法就换一群人。")
    print("   · RESOLUTION  →  面板是 N 个问题上的一个粗量化器。")
    print()
    print("  ⚠️ LIMITATION（这段是仪器的边界，不是免责声明）：")
    print("     这个脚本测的全部是**结构层**：谁发言、什么顺序、多大声。")
    print("     它**没有**测人格内容对台词的影响，因为那需要真的调一次模型。")
    print("     所以 PROBE 4 / 8 的 0% 说明「结构层与人格层是解耦的」，")
    print("     **不**说明「人格没用」。两个结论看起来一样，证据完全不同。")
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
    ap.add_argument("--topics", help="逗号分隔的话题；不给就用默认的 21 个")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()
    topics = ([t.strip() for t in args.topics.split(",") if t.strip()]
              if args.topics else DEFAULT_TOPICS)
    report(topics, as_json=args.json)


if __name__ == "__main__":
    main()
