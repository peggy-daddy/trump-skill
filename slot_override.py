#!/usr/bin/env python3
"""
slot_override.py —— **高权重能不能强抢一个位置？**（@vina 的压力测试）

> @vina: "If the roster is derived but the routing table is static, weights might
> act as a filter rather than a sequencer. To test if high scores can actually
> force a slot override, we should run a stress test: artificially inflate a
> low-priority persona's weight to an extreme outlier and observe if it displaces
> a top-tier persona in the sequence, or if it simply stays stuck in its assigned
> slot despite the score."

⚠️ **这个问题问的不是「名册顺序」（weight_vs_index 已经答过了），
问的是「**台上的位子**」—— 名册顺序 ≠ 上台顺序。**
把两个问题混成一谈，就会得出「权重驱动」这种**到处都成立**的答案。

本探针测 **@vina 说的那个量**，**分路径测**（答案不是唯一的）。
关键设计：**同一个人要分两种情况问**：
  - **他在那张路由表里** → 他本来就在台上 → 拉高他，看他能不能**往前挤**。
  - **他不在那张路由表里** → 拉高他，看他能不能**挤进来**。
  这是两种不同机制，混在一起测会得出「测不出来」这种废结论。

  [0b] **路径自检**：每一节开跑前先断言自己走的是哪条路径
       （静态表 / 动态语料 / 兜底）—— **否则一节测错，整份报告的标签全错**，
       而数字看着还挺像样。（第一版就栽在这：话题命中了动态语料，
       我却把结果标成「静态路径」。）
  [1]  **可分性**：台上的顺序 vs 名册的顺序，是不是同一个序？
  [2]  **静态路径 · 表内成员**：拉高一个**类别里分数最低**的人
       → 他能挤掉同类别里的高分者吗？还是**卡在自己的槽位**？
  [3]  **静态路径 · 表外人员**：拉高一个**根本不在那张表里**的人 → 他能挤进来吗？
  [4]  **兜底路径**：同一个变异 → 兜底按力量取前 3 → 高权重**能不能挤掉名册前排**？
  [5]  **补位路径**：路由表点名的人不在名册 → 补位按**签名 reserve 顺序**还是**力量排序**？
       → 这一格是 @solanize 点名的边界：**「偏好搜索优化的那个量」会不会直接接到面板上**。
  [6]  **负控**：一组**必须变**的变异（探针能红）+ 一组**必须不变**的变异（不过度敏感）。

⚠️ **本探针调用生产实现**（`demo.choose` / `demo.roster_order`），**不重写一遍排序**
—— 一个「重写了被测对象」的探针永远测不到被测对象的改变（我自己的老教训，
见 weight_vs_index.py 开头）。
"""

import copy
import itertools
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import demo  # noqa: E402

OUTLIER = 999.0

# 每个类别里，**确实命中静态路由表**的话题。
# ⚠️ 不能随便拼关键词：动态语料会**先**命中，抢在静态表前面
#   （第一版用 "military iran dominance" → 命中的是动态语料 military-se，
#    我却把结果标成「静态路径」→ **整节标签全错**）。
# → 这些话题是**逐个验证过**命中静态表的。
STATIC_TOPIC = {
    "military": "military war",
    "deal": "tariff negotiat",
    "media": "fake news 媒体",
    "ego": "me 最强",
    "rival": "illegal enemy",
    "family": "family fred",
    "money": "real estate property",
    "policy": "president bill",
    "tech": "tiktok chip",
}


def load_profile():
    with open(os.path.join(ROOT, "data", "trump-profile.json"), encoding="utf-8") as f:
        return json.load(f)


def load_topic_memory():
    with open(os.path.join(ROOT, "data", "topic-memory.json"), encoding="utf-8") as f:
        return json.load(f)


def inflate(profile, key, score):
    """把某人的力量值改成一个极端离群值（**只改分数，不改任何别的**）。"""
    m = copy.deepcopy(profile)
    m["tenGods"][key]["score"] = score
    return m


def weight_order(keys, tg):
    return [k for k, _ in sorted(((k, tg[k]) for k in keys),
                                  key=lambda kv: (-kv[1].get("score", 0),
                                                  kv[1].get("roster_rank", 999)))]


def path_of(src):
    if "动态语料" in src:
        return "dynamic"
    if "静态路由表" in src:
        return "static"
    return "fallback"


def main():
    prof = load_profile()
    tm = load_topic_memory()
    tg = prof["tenGods"]

    print("=" * 74)
    print("SLOT OVERRIDE —— 高权重能不能强抢一个位置？（@vina）")
    print("=" * 74)

    # ── 选类别 / 被试者 ──
    # 类别：任意一个**有静态话题**的类别（话题已逐个验证命中静态表）
    cat = "deal"
    topic = STATIC_TOPIC[cat]
    gods, label = demo.STATIC_ROUTING[cat]
    declared = [g for g in gods if g in tg]

    subject = min(declared, key=lambda k: tg[k].get("score", 0))
    outsiders = [k for k in tg if k not in declared]
    outsider = min(outsiders, key=lambda k: tg[k].get("score", 0)) if outsiders else None

    print(f"\n[0] 被试者")
    print(f"    测试类别：{cat}（{label}）→ 台上声明顺序 {' > '.join(declared)}")
    print(f"    表内被试者：{subject}（分 {tg[subject].get('score')}，"
          f"声明第 {declared.index(subject) + 1} 位 / 共 {len(declared)} 位）")
    if outsider:
        print(f"    表外被试者：{outsider}（分 {tg[outsider].get('score')}，"
              f"**不在 {cat} 表里**）")

    # ── [0b] 路径自检 ──
    _keys0, _src0 = demo.choose(topic, prof, tm)
    p0 = path_of(_src0)
    print(f"\n[0b] 路径自检：'{topic}' → 走的是「{_src0[:40]}」")
    print(f"     → {'**静态路径**（下面第 2/3 节有效）' if p0 == 'static' else '⚠️ **不是静态路径**（第 2/3 节无效！）'}")
    if p0 != "static":
        print("     → **本探针的静态两节作废**，结论只能报兜底/补位部分。")

    m_inf = inflate(prof, subject, OUTLIER)

    # ── [1] 可分性 ──
    print("\n[1] 可分性：名册顺序 vs 台上顺序")
    roster = demo.roster_order(prof)
    by_weight = weight_order(declared, tg)
    distinguishable = (declared != by_weight)
    print(f"    名册序（前 5）         : {' > '.join(roster[:5])}")
    print(f"    台上序（{cat} 声明）   : {' > '.join(declared)}")
    print(f"    台上序（{cat} 按力量） : {' > '.join(by_weight)}")
    print(f"    → 两种序{'**不同** → 有分辨力' if distinguishable else '**相同** → **没有分辨力**'}")

    # ── [2] 静态路径 · 表内成员 ──
    print(f"\n[2] 静态路径 · 表内成员被拉高（{subject} → {OUTLIER:.0f}）")
    base_keys, base_src = demo.choose(topic, prof, tm)
    inf_keys, inf_src = demo.choose(topic, m_inf, tm)
    print(f"    基准  {base_keys}  ← {path_of(base_src)}")
    print(f"    离群  {inf_keys}  ← {path_of(inf_src)}")
    static_member_changed = (base_keys != inf_keys)
    if static_member_changed:
        print(f"    → **变了** —— 他在静态路径上**抢到了位**")
    else:
        print(f"    → **没变** —— 他**卡在自己的槽位**，分数再高也不动"
              f"（声明第 {declared.index(subject) + 1} 位 → 仍是第 "
              f"{inf_keys.index(subject) + 1 if subject in inf_keys else '—'} 位）")
    print(f"    → 对照：名册序{'**变了**' if demo.roster_order(prof) != demo.roster_order(m_inf) else '**没变**'}"
          f"（名册层），台上{'**变了**' if static_member_changed else '**没变**'}"
          f" → **名册层与台上层不是同一个机制**")

    # ── [3] 静态路径 · 表外人员 ──
    static_outsider_changed = None
    if outsider:
        print(f"\n[3] 静态路径 · 表外人员被拉高（{outsider} → {OUTLIER:.0f}）")
        m_out = inflate(prof, outsider, OUTLIER)
        o_keys, o_src = demo.choose(topic, m_out, tm)
        print(f"    基准  {base_keys}")
        print(f"    离群  {o_keys}  ← {path_of(o_src)}")
        static_outsider_changed = (base_keys != o_keys)
        if static_outsider_changed:
            print(f"    → **变了** —— 表外的人**挤进来了**")
        else:
            print(f"    → **没变** —— 表外的人**挤不进来**（路由表是静态的）")

    # ── [4] 兜底路径 ──
    print("\n[4] 兜底路径（无关键词命中）")
    ftopic = "zzz qqq 完全不命中的话题 xxx"
    f_base, f_src = demo.choose(ftopic, prof, tm)
    f_inf, f_src2 = demo.choose(ftopic, m_inf, tm)
    print(f"    基准  {f_base}  ← {path_of(f_src)}")
    print(f"    离群  {f_inf}  ← {path_of(f_src2)}")
    fallback_changed = (f_base != f_inf)
    if fallback_changed:
        pos_b = (f_base.index(subject) + 1) if subject in f_base else None
        pos_i = (f_inf.index(subject) + 1) if subject in f_inf else None
        print(f"    → **变了**：{subject} 基准第 {pos_b or '—'} 位 → 离群第 {pos_i} 位")
        displaced = [k for k in f_base if k not in f_inf]
        if displaced:
            print(f"    → **挤掉**：{' / '.join(displaced)}（基准里力量更高的人被挤下场）")
        print(f"    → 兜底路径上，权重是**顺序器**（能决定谁上台、挤掉谁）")
    else:
        print(f"    → **没变** —— 兜底路径上权重也抢不到位（探针**没分辨力**）")

    # ── [5] 补位路径 ──
    # ⚠️ **两个假设必须给出不同答案，这一节才有分辨力。**
    #   删 1 个人时「签名 reserve 第一个」和「力量最高」常常是**同一个人**
    #   → 测出来「两个假设都成立」→ **没有分辨力**（第一版就栽在这：
    #   bijian 既是 reserve[0] 又是力量 5.0 第一名）。
    # → 所以这里**搜索**一个可分的删除组合，而不是随手挑一个。
    print("\n[5] 补位路径（路由表点名的人不在名册里 → 补位）")
    pol = json.load(open(os.path.join(ROOT, "data", "policy.json"), encoding="utf-8"))
    reserve = pol.get("reserve") or []
    print(f"    签名 reserve（前 5）: {' > '.join(reserve[:5])}")
    separating = None
    for c, t in STATIC_TOPIC.items():
        cg = demo.STATIC_ROUTING[c][0]
        for k in range(1, len(cg)):
            for drops in itertools.combinations(cg, k):
                m = copy.deepcopy(prof)
                for d in drops:
                    del m["tenGods"][d]
                keys, src = demo.choose(t, m, tm)
                if path_of(src) != "static":
                    continue
                called = set(cg) - set(drops)
                res = [x for x in reserve if x in m["tenGods"] and x not in called]
                powr = [z for z in sorted(m["tenGods"],
                                          key=lambda z: (-m["tenGods"][z].get("score", 0),
                                                         m["tenGods"][z].get("roster_rank", 999)))
                        if z not in called]
                if res and powr and res[0] != powr[0]:
                    separating = (c, t, drops, keys, res[0], powr[0], m)
                    break
            if separating:
                break
        if separating:
            break

    by_reserve = by_power = None
    if separating:
        c, t, drops, keys, res_first, pow_first, m = separating
        print(f"    可分案例：类别 {c}，从名册删掉 {' / '.join(drops)}")
        print(f"    台上 {keys}")
        backfilled = [x for x in keys if x not in demo.STATIC_ROUTING[c][0]]
        print(f"    补位的人: {' / '.join(backfilled) if backfilled else '（无）'}")
        by_reserve = (backfilled[0] == res_first) if backfilled else None
        by_power = (backfilled[0] == pow_first) if backfilled else None
        print(f"    签名 reserve 里第一个该补位的人: {res_first}"
              f"（分 {m['tenGods'][res_first].get('score')}）")
        print(f"    力量最高的人: {pow_first}"
              f"（分 {m['tenGods'][pow_first].get('score')}）")
        print(f"    → 两个假设**可分**（{res_first} ≠ {pow_first}）→ 本节**有分辨力**")
        print(f"    → 实际补的是: {backfilled[0] if backfilled else '—'}")
        print(f"    → 补位按**签名顺序**？{'**是**' if by_reserve else '否'}")
        print(f"    → 补位按**力量排序**？{'**是**' if by_power else '**否**'}")
        print(f"    → 判据：**{'签名顺序（力量被挡在门外）' if by_reserve and not by_power else '力量排序（偏好搜索能买到席位！）' if by_power else '两者都不是'}**")
    else:
        print("    ⚠️ 找不到可分案例 → 本节 **INCONCLUSIVE**")

    # ── [6] 负控 ──
    print("\n[6] 负控")
    # 6a 必须红：把**兜底第 1 名**打到 -999 → 兜底必须换人
    m_low = copy.deepcopy(prof)
    m_low["tenGods"][f_base[0]]["score"] = -999.0
    n_base, _ = demo.choose(ftopic, prof, tm)
    n_low, _ = demo.choose(ftopic, m_low, tm)
    red_a = (n_base != n_low)
    print(f"    6a 把兜底第 1 名 {f_base[0]} 打到 -999 → 台上"
          f"{'**变了**（探针**能红**）' if red_a else '⚠️ 没变（探针**测不出来**）'}")

    # 6b 必须绿：改一个**根本不在兜底前 3 里**的人 → 前 3 不该变。
    # ⚠️ 第一版改的是「前 3 里的人」→ 台上当然会变（他掉出去了）
    #   → 那是**正确行为**，不是「过度敏感」。白报一次假红。
    m2 = copy.deepcopy(prof)
    out3 = next((k for k in tg if k not in f_base), None)
    green_b = None
    if out3:
        m2["tenGods"][out3]["score"] = -999.0
        g_base, _ = demo.choose(ftopic, prof, tm)
        g2, _ = demo.choose(ftopic, m2, tm)
        green_b = (g_base[:3] == g2[:3])
        print(f"    6b 把**不在兜底前 3 里**的 {out3} 打到 -999 → 前 3"
              f"{'**不变**（探针**不过度敏感**）' if green_b else '⚠️ 变了（探针**过度敏感**）'}")

    # 6c 必须绿：静态路径上，**表外的人**拉爆 → 台上不该变（路由表是静态的）
    green_c = None
    if outsider and p0 == "static":
        m3 = inflate(prof, outsider, OUTLIER)
        s3, _ = demo.choose(topic, m3, tm)
        green_c = (base_keys == s3)
        print(f"    6c 把**不在 {cat} 表里**的 {outsider} 拉到 999 → 静态路径的台上"
              f"{'**不变**（探针**不过度敏感**）' if green_c else '⚠️ 变了（探针**过度敏感**）'}")
    elif outsider:
        print("    6c 跳过（静态话题自检没过 → 静态那节无效，不能拿来当负控）")

    # ── 结论 ──
    print("\n" + "=" * 74)
    v = []
    if not distinguishable:
        v.append("**INCONCLUSIVE**（名册序 == 台上序 → 无分辨力）")
    if p0 == "static":
        v.append(f"静态·表内：权重 = {'**顺序器**（抢到了位）' if static_member_changed else '**过滤器**（卡在自己的槽位）'}")
        if static_outsider_changed is not None:
            v.append(f"静态·表外：权重 = {'**顺序器**（挤进来了）' if static_outsider_changed else '**过滤器**（挤不进来）'}")
    v.append(f"兜底：权重 = {'**顺序器**（挤掉了前排）' if fallback_changed else '**过滤器**'}")
    if by_reserve is not None:
        v.append(f"补位：按{'**签名顺序**' if by_reserve else '**力量排序**'}")
    print("；".join(v))
    if not red_a:
        print("⚠️ 负控 6a 没红 → **本探针的结论不可信**")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
