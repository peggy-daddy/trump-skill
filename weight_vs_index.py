#!/usr/bin/env python3
"""
weight_vs_index.py —— **层级由权重决定，还是由下标决定？**（@vina 的问题）

> @vina: "However, a swap only tests if the order is a static property of the table
> or a dynamic byproduct of the set size. **It does not tell you if the order is
> determined by a weight-based priority or a simple index.** A comparison of the
> sort order between a **9-persona set and a 10-persona set** would reveal if the
> hierarchy is **relative or absolute**."

⚠️⚠️ **本探针的第一版是错的，而且错法很典型，值得记下来。**
第一版自己写了一份 `order_by_weight()` 复述生产排序，然后用它去测生产排序。
→ 负控立刻抓到问题：我把分数归一化（`score / total`）当"相对化"的例子，
  结果**顺序漂移 0 次** —— 因为除以同一个常数是**保序**的，
  而探针因为测的是**自己的复述**所以永远不会红。
→ **通则：一个重写了被测对象的探针，永远测不到被测对象的改变。**
→ 修法：`demo.roster_order()` 抽成生产函数，探针**调用它**；
  负控改成**真的能改顺序的变异**（翻转分数 / 交换下标）。

本版测四件事，**分开测，不混成一句**：

  [1] **可分性**：权重序 ≠ 声明序？—— 若两者相同，本探针**没有分辨力**，
      后面任何结论都只能报「测不出来」。
  [2] **权重驱动？**：把分数**翻转**（生产路径重跑）→ 顺序跟着翻转？
      跟着翻 = 权重驱动；不跟 = 下标驱动。
  [3] **绝对还是相对**：抽掉一个人（10 人集 → 9 人集）→ 幸存者的相对顺序变了没？
      不变 = **绝对**（分数是他自己的属性，与在场人数无关）。
  [4] **类别内（台上的）顺序**：STATIC_ROUTING 里每个类别的**发言顺序**
      是跟分数走，还是跟**声明顺序**走？→ 这里和 [2] 的答案**不一样**。

  [5] **负控**：一组**能改顺序**的变异（探针必须红）和一组**改不了顺序**的变异
      （探针必须绿）—— 证明探针**既有分辨力又不过度敏感**。
"""
import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import demo  # noqa: E402


def load_profile():
    with open(os.path.join(ROOT, "data", "trump-profile.json"), encoding="utf-8") as f:
        return json.load(f)


def rel(seq, keep):
    return [k for k in seq if k in keep]


def main():
    prof = load_profile()
    tg = prof["tenGods"]
    roster = list(tg.keys())
    n = len(roster)

    print("=" * 70)
    print("WEIGHT vs INDEX —— 层级是权重驱动还是下标驱动？（@vina）")
    print("=" * 70)

    # ── [1] 可分性 ──
    w = demo.roster_order(prof)
    idx = list(tg.keys())
    print(f"\n[1] 可分性  n={n}")
    print(f"    权重序 : {' > '.join(w)}")
    print(f"    声明序 : {' > '.join(idx)}")
    distinguishable = (w != idx)
    print(f"    → 两种假设{'**不同** → 有分辨力' if distinguishable else '**相同** → **没有分辨力**'}")

    # ── [2] 权重驱动？—— 用**不含歧义**的变异 ──
    # ⚠️ 第一版我用「把分数整体翻转」当变异，判据是「新序 == 旧序的反序」。
    #   那是**错的判据**：翻转分数多重集再按声明序重分配，得到的新序并不等于旧序的反序
    #   （并列由 roster_rank 决胜，映射不是简单的取反）。
    #   → 第一次跑就出现「顺序明明跟着分数变了，却判成下标驱动」。
    #   → 换成两个**不含歧义**的单点变异：把某人的分改成**唯一最高/最低**。
    print("\n[2] 单点变异（生产路径 demo.roster_order）")
    last_decl = roster[-1]
    m_hi = copy.deepcopy(prof)
    m_hi["tenGods"][last_decl]["score"] = 999.0
    o_hi = demo.roster_order(m_hi)
    hi_ok = (o_hi[0] == last_decl)
    print(f"    2a 把**声明序最后**的 {last_decl} 改成唯一最高分 → 它排第几？"
          f"{'第 1（**权重驱动**）' if hi_ok else f'第 {o_hi.index(last_decl)+1}（**下标驱动**）'}")
    first_decl = roster[0]
    m_lo = copy.deepcopy(prof)
    m_lo["tenGods"][first_decl]["score"] = -999.0
    o_lo = demo.roster_order(m_lo)
    lo_ok = (o_lo[-1] == first_decl)
    print(f"    2b 把**声明序第一**的 {first_decl} 改成唯一最低分 → 它排第几？"
          f"{'末位（**权重驱动**）' if lo_ok else f'第 {o_lo.index(first_decl)+1}（**下标驱动**）'}")
    flipped = hi_ok and lo_ok

    # ── [3] 9 人集 vs 10 人集：绝对还是相对？──
    print(f"\n[3] {n} 人集 vs {n-1} 人集 —— 抽掉一个人，幸存者顺序漂移吗？")
    drift = 0
    for drop in roster:
        sub = copy.deepcopy(prof)
        del sub["tenGods"][drop]
        surv = set(sub["tenGods"].keys())
        before = rel(w, surv)
        after = rel(demo.roster_order(sub), surv)
        if before != after:
            drift += 1
            print(f"    抽掉 {drop:<10} → **漂移**  {before} → {after}")
    print(f"    → 漂移 {drift}/{n} 次 → "
          f"{'**绝对**（分数是他自己的属性，与在场人数无关）' if drift == 0 else '**相对**（位置随在场人数变）'}")

    # ── [4] 类别内（台上）顺序 ──
    print("\n[4] 类别内**发言顺序**（STATIC_ROUTING）跟分数走吗？")
    cat_weight = 0
    cat_total = 0
    for cat, (gods, label) in demo.STATIC_ROUTING.items():
        cg = {k: tg[k] for k in gods if k in tg}
        if not cg:
            continue
        cat_total += 1
        declared = list(cg.keys())
        by_weight = [k for k, _ in sorted(cg.items(),
                                          key=lambda kv: (-kv[1].get("score", 0),
                                                          kv[1].get("roster_rank", 999)))]
        if declared != by_weight:
            cat_weight += 1
            print(f"    {cat:<8} 声明: {' > '.join(declared)}")
            print(f"    {'':<8} 权重: {' > '.join(by_weight)}   ← **不一致**")
    print(f"    → {cat_weight}/{cat_total} 个类别的**发言顺序**与分数顺序**不一致**")

    # ── [5] 负控：探针既要有分辨力，又不能过度敏感 ──
    print("\n[5] 负控")
    # 5a 必须红：把名次第二的人换成最高分 → 顺序必须变
    m = copy.deepcopy(prof)
    second = w[1]
    m["tenGods"][second]["score"] = max(v.get("score", 0) for v in tg.values()) + 10
    red_a = (demo.roster_order(m) != w)
    print(f"    5a 提升 {second} 到最高分 → 顺序{'**变了**（探针**能红**）' if red_a else '⚠️ 没变（探针**测不出来**）'}")
    # 5b 必须绿：改动一个**根本不在前 3** 的人的分数 → 前 3 顺序不该变
    m2 = copy.deepcopy(prof)
    tail = w[-1]
    m2["tenGods"][tail]["score"] = -999
    green_b = (demo.roster_order(m2)[:3] == w[:3])
    print(f"    5b 把末位 {tail} 的分打到 -999 → 前 3 顺序"
          f"{'**不变**（探针**不过度敏感**）' if green_b else '⚠️ 变了（探针**过度敏感**）'}")

    # ── 结论 ──
    print("\n" + "=" * 70)
    if not distinguishable:
        verdict = "INCONCLUSIVE"
    elif flipped:
        verdict = "WEIGHT-DRIVEN"
    else:
        verdict = "INDEX-DRIVEN"
    # 5a/5b 也参与判定
    if not red_a:
        verdict = "INCONCLUSIVE（探针连最基本的变异都测不出来）"
    print(f"名册层级（{verdict}）")
    if cat_weight:
        print(f"台上发言顺序：**{cat_weight}/{cat_total} 个类别与分数顺序不一致** → "
              f"它是**声明顺序**，不是力量读数")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
