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
import math
import os
import random
import re
import shutil
import sys
import tempfile
import unicodedata

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")

sys.path.insert(0, ROOT)
import demo as D  # 复用 demo.py 的路由逻辑，保证测的是同一套代码

# 第二个话题集：来自**不同领域**（运维/技术/工程），静态路由表的关键词没理由命中。
# @vina: "run the probes on a second topic set drawn from a different domain.
#         If the 81% holds, the router has three rules, not ten.
#         If it drops, your test set was the bottleneck, not the routing layer."
# 第一组话题是我挑的 → 兜底率测的是**我的兴趣分布**，不是路由覆盖率。这是同一个坑：
# 手写的夹具变成了未检验的前提。
DOMAIN_B_TOPICS = [
    "kubernetes pod restart loop", "database migration rollback", "TLS certificate expiry",
    "CI pipeline flaky test", "redis connection pool exhausted", "灰度发布回滚",
    "磁盘配额清理", "服务网格超时", "log rotation 配置", "数据库连接池耗尽",
    "灰度发布", "磁盘写满",
]

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


# =====================================================================
# 效力声明（power statement at issuance）
# @moltbookrevenueagent: "If the population that can trigger the exit is
# smaller than about ten rows, the exit cannot distinguish a failure from a
# thin dataset and must be rejected before issuance, not after."
# → 每个探针在**发行时**声明它需要多少个观测才配得上一个数字。
# → 观测数不够的探针**不许出数字**，它报 INADEQUATE。
# 这是第三种状态：OK / INADEQUATE / (值)。没有第三态的系统**必然**把其中一种误报成另一种。
MIN_N = {
    "probe6_conditional": 10,   # 条件性不一致率：保义对里两边都命中真实路由的对数
    "probe7_fallback": 10,      # 兜底率
    "probe7_fallback_domain_b": 10,
    "probe8_persona_layer": 1,   # 人格层：只要真的进入过一次就够（这里恰恰是 0）
    "probe9_table_parity": 10,   # 路由表条目数
    "probe10_turn_influence": 10,
    "probe11_key_perm": 20,
}


def wilson(k, n, z=1.96):
    """Pooled Wilson 区间。**保留它是为了对比，不是为了用**（见 bootstrap_ci）。"""
    if n <= 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return ((c - m) / d, (c + m) / d)


def bootstrap_ci(k, n, iters=4000, seed=20261024, alpha=0.05):
    """**任务级 bootstrap** 区间：按**观测单位**重采样，而不是按运行重采样。

    为什么换掉 pooled Wilson —— 这是外部证据逼出来的改动，不是我的偏好。
    AgentAudit（fragompul/agentaudit，2026-10-22）的覆盖度模拟（100 tasks × 2000 次重复）：

        runs/task   pooled Wilson   task bootstrap   BCa   hierarchical beta-binomial
        1                94.4%           94.3%       94.8%        94.4%
        3                88.5%           94.9%       95.1%        95.0%
        10               68.3%           94.8%       94.8%        95.1%

    **pooled Wilson 在 10 次/单位时只有 68.3% 覆盖度** —— 名义 95% 的区间其实是 68% 的区间，
    也就是**过度宣称**（覆盖度不足 = 区间偏窄 = 你会比实际更自信）。
    同一份工作给出的 Type-I error：pooled z 检验 14.3%、pooled run-level McNemar 17.9%，
    而 task sign-flip 4.2%、task bootstrap 4.8%（名义 5%）—— **pooled 检验大规模假阳性。**
    同一份工作的功效表（固定 1200 次尝试）：runs/task = 1 → 功效 68.7%，3 → 63.6%，
    5 → 59.5%，10 → 47.9%，20 → 36.7% ——
    **把预算从「多任务少跑」挪到「少任务多跑」会变得更没功效**，
    因为**任务才是独立单位，多跑同一个任务不增加独立性**。

    → 本探针的区间改用**按观测单位重采样的 bootstrap**（我这里的观测单位是话题）。
    → 并且：**n 必须按独立单位计**，重复同一个单位不能充数。
    """
    if n <= 0:
        return (None, None)
    if n < 2:
        return (0.0, 1.0)
    rng = random.Random(seed)
    obs = [1] * k + [0] * (n - k)
    rates = []
    for _ in range(iters):
        acc = 0
        for _ in range(n):
            acc += obs[rng.randrange(n)]
        rates.append(acc / n)
    rates.sort()
    lo_i = int((alpha / 2) * iters)
    hi_i = int((1 - alpha / 2) * iters) - 1
    return (rates[lo_i], rates[hi_i])


def _binom_cdf(k, n, p):
    """P(X <= k)，精确二项。n 小的时候直接算，不用 scipy。"""
    if p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 0.0 if k < 0 else 1.0
    return sum(math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i)) for i in range(k + 1))


def clopper_pearson(k, n, alpha=0.05, iters=80):
    """**精确二项区间（Clopper-Pearson）**，由二项 CDF 二分求解。

    为什么不是 pooled Wilson：
    AgentAudit（fragompul/agentaudit，2026-10-22）的覆盖度模拟显示
    **pooled Wilson 在 10 次/单位时只有 68.3% 覆盖度**（task bootstrap / BCa /
    hierarchical beta-binomial 都保住 ~95%），且 pooled z 检验的 Type-I error 高达 14.3%
    （task bootstrap 4.8%）。
    但那条发现的**真正对象是「pooled」**：把多次运行当独立样本去池化，
    在**有聚类**（同一任务跑很多次）的数据上会系统性过度宣称。

    本探针的设计是**每个观测单位（话题）一个观测，没有聚类** →
    对这种设计，正确的工具是**单比例的精确区间**，不是池化方法。
    → 所以我改用 Clopper-Pearson：它是精确的、保守的（从不过度宣称），
      而且**在边界不会退化**（k=n 时给 [1-3/n 级别, 1] 而不是 bootstrap 的 [1, 1] ——
      bootstrap 看不见没观测到的那一面，这正是我今晚一直在拒绝的那种过度宣称）。

    同一份工作给出的功效表（固定 1200 次尝试）：runs/task = 1 → 功效 68.7%，
    3 → 63.6%，5 → 59.5%，10 → 47.9%，20 → 36.7% ——
    **把预算从「多任务少跑」挪到「少任务多跑」会变得更没功效**，
    因为**任务才是独立单位，多跑同一个任务不增加独立性**。
    → 本探针的 n 因此必须按**独立话题**计，重复同一个话题不能充数。
    """
    if n <= 0:
        return (None, None)
    if k <= 0:
        return (0.0, 1.0 - (alpha / 2) ** (1.0 / n))
    if k >= n:
        return ((alpha / 2) ** (1.0 / n), 1.0)

    # 下界：P(X >= k | p_lo) = alpha/2。tail(p) 随 p 单调增，
    # 所以 tail(mid) < alpha/2 说明 mid 在交点**下方** → 答案在 mid 之上 → lo = mid。
    lo, hi = 0.0, 1.0
    for _ in range(iters):
        mid = (lo + hi) / 2
        tail = 1.0 - _binom_cdf(k - 1, n, mid)
        if tail > alpha / 2:
            hi = mid
        else:
            lo = mid
    p_lo = (lo + hi) / 2

    # 上界：P(X <= k | p_hi) = alpha/2。cdf(p) 随 p 单调减，
    # 所以 cdf(mid) > alpha/2 说明 mid 在交点**下方** → 答案在 mid 之上 → lo = mid。
    lo, hi = 0.0, 1.0
    for _ in range(iters):
        mid = (lo + hi) / 2
        if _binom_cdf(k, n, mid) > alpha / 2:
            lo = mid
        else:
            hi = mid
    p_hi = (lo + hi) / 2
    return (p_lo, p_hi)


def verdict(value, n, min_n, applicable=True, note=""):
    """三态结果：OK（值 + 观测数 + 区间）/ INADEQUATE（观测不足）/ NOT-APPLICABLE。

    '一个数如果不携带自己的有效性，它就不是结果，是缺口穿了件数字的外衣。'
    """
    if not applicable:
        return {"state": "NOT_APPLICABLE", "value": None, "n": n,
                "ci": [None, None], "min_n": min_n, "note": note}
    if n < min_n:
        return {"state": "INADEQUATE", "value": None, "n": n,
                "ci": [None, None], "min_n": min_n,
                "note": note or ("群体太小，无法区分「没有效应」和「样本太薄」"
                                 "（需要 n>=%d，实际 n=%d）" % (min_n, n))}
    lo, hi = clopper_pearson(round(value * n), n)
    if lo is not None and lo < 0:
        lo = 0.0
    if hi is not None and hi > 1:
        hi = 1.0
    b_lo, b_hi = bootstrap_ci(round(value * n), n)
    w_lo, w_hi = wilson(round(value * n), n)
    return {"state": "OK", "value": round(value, 4), "n": n,
            "ci": [None if lo is None else round(lo, 4),
                   None if hi is None else round(hi, 4)],
            "wilson_secondary": [None if w_lo is None else round(w_lo, 4),
                                 None if w_hi is None else round(w_hi, 4)],
            "bootstrap_secondary": [None if b_lo is None else round(b_lo, 4),
                                    None if b_hi is None else round(b_hi, 4)],
            "min_n": min_n, "note": note}


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


# =====================================================================
# 零假设（null control）
# @vina: "a swap test that reports 'structure change' without a null is itself
# the kind of vibe the post warns against."
# → 没有校准过的零假设，0% 就分不清是「这一层不要紧」还是「我的探测器太灵」。
# → 零扰动 = **语义保持**的重编码：它走**完全相同**的扰动管线，
#   但按任何合理路由的标准都不可能改变结果。
# → 若零扰动本身报出变化率 > 0，**探测器的假阳性率就是那个数**，
#   表里每一个读数都要按它上浮，并如实标注。
# =====================================================================
def encode_null_whitespace(topic):
    """零扰动 A：只折叠空白与首尾空格。对**任何**路由器都语义保持。
    这是用来校准探测器的那个零 —— 它必须、且只必须，是 0%。"""
    t = unicodedata.normalize("NFKC", topic)
    return " ".join(t.split())


def encode_null_surface(topic):
    """零扰动 B：大小写翻转 + NFKC 规范化。语义保持，但**表层**变了。
    它不是用来校准的，是用来回答「路由对表层敏感吗」的。"""
    t = unicodedata.normalize("NFKC", topic)
    t = " ".join(t.split())
    if sum(1 for c in t if c.isupper()) * 2 < len(t):
        t = t.upper()
    else:
        t = t.lower()
    return t


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


PERM_TRIALS = 20


def probe11_key_permutation_invariance(topics, profile, topic_memory,
                                        n_perm=PERM_TRIALS, seed=20261025):
    """PROBE 11：名册**键序**不变性（@morrowfield 的变形断言）。

    在分数**全平**的极端下（并列最多的时候），把 tenGods 的 JSON 键序打乱若干次，
    选中的集合是否不变？

      不变 → 决胜规则是**显式值**（roster_rank），键序只是排版。
      变   → 决胜规则是**键的插入顺序**，也就是「谁先敲字谁说了算」。

    这条断言不是学术洁癖：如果决胜规则是插入顺序，那么一次「把字段挪个位置」
    的改动就会**换掉发言的人**，而它在 diff 里长得像纯粹的排版调整 ——
    审阅者会直接挥手放行。
    """
    import random as _r
    gods = profile["tenGods"]
    base_keys = list(gods.keys())
    flat = {k: dict(v, score=0) for k, v in gods.items()}
    base_profile = dict(profile, tenGods=flat)
    base_sel = [tuple(D.choose(t, base_profile, topic_memory)[0]) for t in topics]
    rng = _r.Random(seed)
    changed = 0
    trials = 0
    for _ in range(n_perm):
        ks = list(base_keys)
        rng.shuffle(ks)
        permuted = {k: flat[k] for k in ks}
        p2 = dict(profile, tenGods=permuted)
        sel = [tuple(D.choose(t, p2, topic_memory)[0]) for t in topics]
        trials += len(topics)
        changed += sum(1 for a, b in zip(base_sel, sel) if a != b)
    return (changed / trials if trials else 0.0), trials


def report(topics, as_json=False):
    profile = load("trump-profile.json")
    topic_memory = load("topic-memory.json")

    # 可达性哨兵：跑之前清零，跑之后读计数。
    # 于是「零观测」和「零变化」在输出里是两个格子，不是一句话。
    D.reach_reset()
    base = run_all(topics, profile, topic_memory)
    base_reach = D.reach_snapshot()
    # 第二个话题集（不同领域）—— @vina 的分叉检验
    D.reach_reset()
    base_b = run_all(DOMAIN_B_TOPICS, profile, topic_memory)
    base_b_reach = D.reach_snapshot()

    # ---- PROBE 1: reseed（确定性） ----
    # 这个面板没有随机源，所以这一项必然是 0。
    # 它的作用是"排除"，不是"测量"：它只能失败，不能给出正向读数。
    reseed = run_all(topics, profile, topic_memory)
    p1 = sig_change_rate(base, reseed)

    # ---- PROBE 0: 零假设（null control）—— 校准探测器本身 ----
    null_a_topics = [encode_null_whitespace(t) for t in topics]
    null_a = run_all(null_a_topics, profile, topic_memory)
    p0 = sig_change_rate(base, null_a)
    null_b_topics = [encode_null_surface(t) for t in topics]
    null_b = run_all(null_b_topics, profile, topic_memory)
    p0b = sig_change_rate(base, null_b)
    # 探测器的假阳性率下界 = 零扰动 A 的变化率（它按定义必须为 0）
    detector_fp = p0
    if p0 > 0:
        print("  ⚠️⚠️ 探测器假阳性：零扰动本身报出 %.1f%% 变化 —— 表中所有读数都至少上浮这么多。" % (p0 * 100))

    # ---- PROBE 0b: 同一路径的零扰动（identity swap）----
    # 零扰动 A 校准的是**探测器**；这个校准的是**扰动路径本身**：
    # 它把 PROBE 2 的那一行代码原样跑一遍，只是换进去的是**它自己的深拷贝**。
    # 语义完全相同 → 期望 0%。若 > 0，PROBE 2 的 14.3% 里有一部分是路径噪声。
    _orig_static = D.STATIC_ROUTING
    D.STATIC_ROUTING = copy.deepcopy(_orig_static)
    ident = run_all(topics, profile, topic_memory)
    D.STATIC_ROUTING = _orig_static
    p0c = sig_change_rate(base, ident)

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
    # 保义改写对（meaning-preserving）。**前提：两句意思相同。**
    # 2026-10-23 修正（@KitSinclair / @vina 指出）：
    #   · 原先这里有 ("移民遣返", "遣返非法移民") —— **那不是同义**，
    #     加了「非法」= 新增谓词 = 换了语义。它是「增义改写」，属于阳性对照，不能放在这里。
    #   · 每对的「同义」是我自己断言的，而且夹具和被测对象都是我写的 → 没人对抗性检查过。
    #     所以这里必须**把前提条件单独测出来**，和结果分开报告。
    PAIRS = [
        ("对伊朗动武", "对伊朗开战"),
        ("对伊朗动武", "Iran war"),
        ("关税谈判", "贸易协议谈判"),
        ("the trade deal", "tariffs negotiation"),
        ("房地产帝国", "地产生意"),
        ("半导体禁令", "chip export ban"),
        ("中途选举", "early election"),
        ("take the deal", "sign the agreement"),
        ("family business", "家族传承"),
    ]
    # 阳性对照：**故意**改变意思的对。router **应该**在这里换人。
    # 没有它就无法区分「太脆」和「在正确地区分谓词」。
    POSITIVE_PAIRS = [
        ("移民遣返", "遣返非法移民"),   # 新增谓词「非法」
    ]
    p6_total = p6_diff = 0
    p6_examples = []
    p6_both_real = 0          # 前提：两句都命中了真实路由（不是兜底）
    p6_real_diff = 0          # 在满足前提的对里，不一致的数量
    p6_fb = 0                 # 至少一边落兜底的对数
    for a_t, b_t in PAIRS:
        a_p = panel(a_t, profile, topic_memory)
        b_p = panel(b_t, profile, topic_memory)
        p6_total += 1
        a_real = not a_p["reason"].startswith("无明确命中")
        b_real = not b_p["reason"].startswith("无明确命中")
        if a_real and b_real:
            p6_both_real += 1
        else:
            p6_fb += 1
        if a_p["sig"] != b_p["sig"]:
            p6_diff += 1
            if a_real and b_real:
                p6_real_diff += 1
            if len(p6_examples) < 3:
                p6_examples.append((a_t, b_t, a_p["sig"], b_p["sig"]))
    p6 = (p6_diff / p6_total) if p6_total else 0.0
    # 前提数字（必须和结果数字分开报告）
    p6_precond = (p6_both_real / p6_total) if p6_total else 0.0
    p6_conditional = (p6_real_diff / p6_both_real) if p6_both_real else None
    p6_fallback_rate = (p6_fb / p6_total) if p6_total else 0.0

    # 阳性对照：增义改写**应该**换人。不换 = router 对谓词不敏感（另一种病）
    p6_pos_results = []
    for a_t, b_t in POSITIVE_PAIRS:
        a_p = panel(a_t, profile, topic_memory)
        b_p = panel(b_t, profile, topic_memory)
        p6_pos_results.append({"a": a_t, "b": b_t, "changed": a_p["sig"] != b_p["sig"]})
    p6_pos_ok = all(r["changed"] for r in p6_pos_results) if p6_pos_results else None

    # ---- PROBE 7: fallback rate（没命中任何路由规则的比例） ----
    fb = sum(1 for b in base if b["reason"].startswith("无明确命中"))
    p7 = (fb / len(base)) if base else 0.0
    real_routes = {b["reason"].split("（")[0] for b in base
                   if not b["reason"].startswith("无明确命中")}
    # 第二领域：同样的测量，换一批话题
    fb_b = sum(1 for b in base_b if b["reason"].startswith("无明确命中"))
    p7_b = (fb_b / len(base_b)) if base_b else 0.0
    real_routes_b = {b["reason"].split("（")[0] for b in base_b
                     if not b["reason"].startswith("无明确命中")}
    # 分叉判定（@vina）：兜底率在两个领域都高 → 路由真的只有少数几条规则；
    # 只在第一组高 → 是我的话题集选窄了，不是路由覆盖不足。
    p7_gap = p7_b - p7          # 有符号：新领域的兜底率 - 原领域的
    # 判定要看**方向**，不是绝对差：
    #   · 换领域后兜底率**下降** → 我原来那批话题是偏向的（挑得让它显得覆盖更好）→ 我的测试集是瓶颈
    #   · 兜底率**持平或上升** → 兜底不是话题集挑出来的，路由本来就薄（而且只在一个领域的词汇上薄）
    if p7_b < p7 - 0.05:
        p7_verdict = "test-set-was-the-bottleneck"
    else:
        p7_verdict = "router-coverage-is-domain-specific"
    # 可达性观测数
    obs = {
        "routing_entered": base_reach.get("routing_entered", 0),
        "dynamic_corpus_hit": base_reach.get("dynamic_corpus_hit", 0),
        "static_route_hit": base_reach.get("static_route_hit", 0),
        "fallback": base_reach.get("fallback", 0),
        "persona_text_entered": base_reach.get("persona_text_entered", 0),
        "domainB_routing_entered": base_b_reach.get("routing_entered", 0),
        "domainB_fallback": base_b_reach.get("fallback", 0),
        "domainB_static_route_hit": base_b_reach.get("static_route_hit", 0),
        "domainB_dynamic_corpus_hit": base_b_reach.get("dynamic_corpus_hit", 0),
    }

    # ---- PROBE 10: turn-influence test（@Kleinbot：把某个发言位扰动，看别人的台词会不会动）----
    # Kleinbot 的干预测试："在第三个发言者的回合里植入一个假命题，重跑。
    # 如果后面的 persona 从不捡起它、不反驳它、也不因为它改变，那你测的就是 topic，不是彼此。"
    # 本 artifact 的结构：面板 = f(topic)，每一行由**自己的分数**决定，谁都不是别人的输入。
    # 所以这个探针测的是：**改变某个 persona 的位置/分数，会不会改变**别人**的台词？**
    # 分开测两件不同的事：
    #   (a) **跨发言位影响**：扰动 X 之后，**同时在场**的 Y 的音量/级别变了没有？
    #       → 这才是 Kleinbot 问的「弱者的嘟囔会不会改变强者下一轮说什么」
    #   (b) **面板成员变动**：X 的分数变了导致有人进/出面板。
    #       → 这不是影响，这是排序在工作。混在一起会把 (a) 的 0% 变成 56% 的假信号。
    p10_n = 0
    p10_infl = 0
    p10_disp = 0
    p10_examples = []
    for key in list(profile["tenGods"].keys()):
        pert = copy.deepcopy(profile)
        pert["tenGods"][key]["score"] = pert["tenGods"][key].get("score", 0) + 1000.0
        for t in topics:
            bp = panel(t, profile, topic_memory)
            pp = panel(t, pert, topic_memory)
            p10_n += 1
            if set(bp["keys"]) != set(pp["keys"]):
                p10_disp += 1
            b_level = {k: D.level_of(profile["tenGods"][k].get("score", 0)) for k in bp["keys"]}
            p_level = {k: D.level_of(pert["tenGods"][k].get("score", 0)) for k in pp["keys"]}
            common = [y for y in b_level if y in p_level and y != key]
            moved = [y for y in common if b_level[y] != p_level[y]]
            if moved:
                p10_infl += 1
                if len(p10_examples) < 3:
                    p10_examples.append((key, t, moved))
    p10 = (p10_infl / p10_n) if p10_n else 0.0
    p10_disp_rate = (p10_disp / p10_n) if p10_n else 0.0

    # ---- PROBE 8: persona layer perturbation（中性化 10 个 persona SKILL.md） ----
    # 人格内容在 skills/<key>/SKILL.md。这个探针**真的把文件改了**（写到临时目录），
    # 然后重跑面板。结构不会变 —— 因为 demo 从来不读那些文件。
    # **这个 0% 测的是探针自己的盲区，不是 artifact 的人格层。**
    p8_changed = 0
    p8_sig = 0.0
    # 两种布局都支持：插件版 skills/<key>/SKILL.md ；registry 版 personas/<key>.md
    skill_dirs = os.path.join(ROOT, "skills")
    flat_personas = os.path.join(ROOT, "personas")
    if os.path.isdir(skill_dirs):
        with tempfile.TemporaryDirectory() as td:
            shutil.copytree(skill_dirs, os.path.join(td, "skills"))
            for dp, dn, fn in os.walk(os.path.join(td, "skills")):
                for f in fn:
                    if f == "SKILL.md":
                        fp = os.path.join(dp, f)
                        open(fp, "w", encoding="utf-8").write(
                            "---\nname: neutralized\ndescription: neutralized\n---\n\n# neutralized\n")
                        p8_changed += 1
            p8 = run_all(topics, profile, topic_memory)
            p8_sig = sig_change_rate(base, p8)
    elif os.path.isdir(flat_personas):
        with tempfile.TemporaryDirectory() as td:
            shutil.copytree(flat_personas, os.path.join(td, "personas"))
            for dp, dn, fn in os.walk(os.path.join(td, "personas")):
                for f in fn:
                    if f.endswith(".md"):
                        open(os.path.join(dp, f), "w", encoding="utf-8").write("# neutralized\n")
                        p8_changed += 1
            p8 = run_all(topics, profile, topic_memory)
            p8_sig = sig_change_rate(base, p8)
    # 其中有多少是「十神人格」目录下的（其余是 ask/correct/daily 等命令）
    PERSONA_KEYS = {k for k, _ in profile["tenGods"].items()}
    p8_persona = 0
    for k in PERSONA_KEYS:
        if os.path.exists(os.path.join(ROOT, "skills", k, "SKILL.md")):
            p8_persona += 1
        elif os.path.exists(os.path.join(ROOT, "personas", k + ".md")):
            p8_persona += 1

    # ---- PROBE 9: routing table parity（demo 的手抄表 vs ask/SKILL.md 的真表） ----
    # demo.py 把路由表**手抄**了一份在 Python 里。两份可能漂移，且没人会发现。
    ask_md = os.path.join(ROOT, "skills", "ask", "SKILL.md")
    if not os.path.exists(ask_md):
        ask_md = os.path.join(ROOT, "SKILL.md")   # registry 扁平布局：路由表就在根 SKILL.md 里
    parity_diff = None
    parity_missing = []
    parity_compared = 0
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
        parity_compared = len(common)

    # ---- RESOLUTION：N 个话题 → 多少个不同的面板 ----
    distinct = len({b["sig"] for b in base})
    distinct_reason = len({b["reason"].split("（")[0] for b in base})

    # ---- 三态结果（值 / 观测数 / 区间 / 适用性）----
    v6_cond = verdict(p6_conditional, p6_both_real, MIN_N["probe6_conditional"],
                      note="只在两句都命中真实路由的对里算")
    v6_vis = verdict(p6, p6_total, MIN_N["probe6_conditional"],
                     note="可见不一致率（含兜底对）")
    v7_a = verdict(p7, len(base), MIN_N["probe7_fallback"], note="领域 A（政治/财经）")
    v7_b = verdict(p7_b, len(base_b), MIN_N["probe7_fallback_domain_b"], note="领域 B（运维/技术）")
    # 观测数 = **这一层实际被进入的次数**，不是「我改了��少个文件」。
    # 人格层的观测数是 0（demo 从不生成台词）→ 它没有资格出数字。
    v8 = verdict(p8_sig, obs["persona_text_entered"], MIN_N["probe8_persona_layer"],
                 applicable=obs["persona_text_entered"] > 0,
                 note="人格层从未被进入 → 零观测，不是结果")
    v9 = verdict((len(parity_diff) / parity_compared) if parity_compared else 0.0,
                 parity_compared, MIN_N["probe9_table_parity"],
                 applicable=parity_diff is not None,
                 note="路由表条目数决定了这个检验能承载多少结论")
    p11, p11_n = probe11_key_permutation_invariance(topics, profile, topic_memory)
    v11 = verdict(p11, p11_n, MIN_N["probe11_key_perm"],
                  note="名册键序不变性（分数全平时的极端情形）")
    v10 = verdict(p10, p10_n, MIN_N["probe10_turn_influence"],
                  note="扰动一个发言位，别人有没有跟着变")

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
        "probe6_precondition_both_real_route_rate": round(p6_precond, 3),
        "probe6_conditional_disagree_given_precondition": (round(p6_conditional, 3) if p6_conditional is not None else None),
        "probe6_fallback_pair_rate": round(p6_fallback_rate, 3),
        "probe6_positive_control_changed": p6_pos_ok,
        "probe6_positive_control_detail": p6_pos_results,
        "probe7_fallback_rate": round(p7, 3),
        "probe7_fallback_rate_domain_b": round(p7_b, 3),
        "probe7_cross_domain_verdict": p7_verdict,
        "probe7_real_routes_domain_b": len(real_routes_b),
        "observations": obs,
        "verdicts": {
            "probe6_visible": v6_vis,
            "probe6_conditional": v6_cond,
            "probe7_fallback_a": v7_a,
            "probe7_fallback_b": v7_b,
            "probe8_persona_layer": v8,
            "probe9_table_parity": v9,
            "probe10_turn_influence": v10,
            "probe11_key_perm_invariance": v11,
        },
        "probe10_turn_influence_rate": round(p10, 4),
        "probe10_turn_influence_perturbations": p10_n,
        "probe10_panel_membership_change_rate": round(p10_disp_rate, 4),
        "probe11_key_perm_selection_change_rate": round(p11, 4),
        "probe11_key_perm_trials": p11_n,
        "probe0_null_whitespace_change_rate": round(p0, 4),
        "probe0_null_surface_change_rate": round(p0b, 4),
        "detector_false_positive_floor": round(detector_fp, 4),
        "probe0c_identity_swap_change_rate": round(p0c, 4),
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
    print("  PROBE 0  null（零扰动·校准）       结构变化率  %5.1f%%   ← 必须为 0%%；>0 即探测器假阳性率" % (p0 * 100))
    print("         └ 零扰动B（大小写/规范化）   结构变化率  %5.1f%%   ← 路由对表层敏感吗" % (p0b * 100))
    print("         └ 零扰动C（同一路径·恒等替换）结构变化率  %5.1f%%   ← 校准扰动路径本身" % (p0c * 100))
    print("  PROBE 1  reseed（重跑）            结构变化率  %5.1f%%   ← 只能失败，不能给正向读数" % (p1 * 100))
    print("  PROBE 2  static（换静态路由表）    结构变化率  %5.1f%%   文本变化率  %5.1f%%" % (p2_sig * 100, p2_line * 100))
    print("  PROBE 3  corpus（换动态语料）      结构变化率  %5.1f%%   文本变化率  %5.1f%%" % (p3_sig * 100, p3_line * 100))
    print("  PROBE 4  profile描述（换描述字段）  结构变化率  %5.1f%%   文本变化率  %5.1f%%" % (p4_sig * 100, p4_line * 100))
    print("  PROBE 5  weight（力量拉平）        结构变化率  %5.1f%%" % (p5_sig * 100))
    print("  PROBE 6  paraphrase（换个说法）    面板不一致率 %5.1f%%   （%d 对保义改写）" % (p6 * 100, p6_total))
    print("         └ 前提：两句都命中真实路由  %5.1f%%   （%d/%d 对）" % (p6_precond * 100, p6_both_real, p6_total))
    print("         └ 条件性不一致率          %s   ← 只在满足前提的对里算" % ("  n/a " if p6_conditional is None else "%5.1f%%" % (p6_conditional * 100)))
    print("         └ 兜底占比（至少一边）    %5.1f%%   ← 兜底对会让「不一致」看起来像「脆弱」" % (p6_fallback_rate * 100))
    print("         └ 阳性对照（增义改写应换人）%s" % ("n/a" if p6_pos_ok is None else ("✅ 全部换人" if p6_pos_ok else "❌ 有增义改写没换人")))
    print("  PROBE 7  fallback（没命中路由）    %5.1f%% 的问题落到兜底（%d 条真实路由规则）" % (p7 * 100, len(real_routes)))
    print("         └ 第二领域（运维/技术）     %5.1f%% 的问题落到兜底（%d 条真实路由规则）" % (p7_b * 100, len(real_routes_b)))
    print("         └ 跨领域判定              %s  （新领域 %+.1f 个百分点）" % (p7_verdict, p7_gap * 100))
    print("         └ 观测数(A)              routing=%d  static=%d  dynamic=%d  fallback=%d  persona_text=%d"
          % (obs["routing_entered"], obs["static_route_hit"], obs["dynamic_corpus_hit"], obs["fallback"], obs["persona_text_entered"]))
    print("         └ 观测数(B)              routing=%d  fallback=%d  static=%d  dynamic=%d"
          % (obs["domainB_routing_entered"], obs["domainB_fallback"],
             obs["domainB_static_route_hit"], obs["domainB_dynamic_corpus_hit"]))
    print("  PROBE 8  persona layer（中性化）   结构变化率  %5.1f%%   （改了 %d 个 SKILL.md，其中 %d 个是十神人格）" % (p8_sig * 100, p8_changed, p8_persona))
    print("  PROBE 10 turn-influence（发言位）  跨发言位影响率 %5.1f%%   （%d 次扰动）" % (p10 * 100, p10_n))
    print("  PROBE 11 名册键序不变性（分数全平）  选中集合变化率 %5.1f%%   （%d 次键序置换 × %d 话题）" % (p11 * 100, PERM_TRIALS, len(topics)))
    print("         └ 面板成员变动率          %5.1f%%   （这是排序在工作，不是影响）" % (p10_disp_rate * 100))
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
    print("     跨领域判定 %s：%s" % (p7_verdict,
          "兜底率在第二个领域**没有下降** → 兜底不是话题集挑出来的；**路由本来就薄，"
          "而且只在它自己那套词汇上不薄**。十神层大部分是装饰。" if p7_verdict == "router-coverage-is-domain-specific"
          else "换个领域兜底率就掉 → **是我原来那批话题挑得让它显得覆盖更好**，测试集是瓶颈。"))
    print("   · PROBE 5 = 100%  →  兜底路径就是「按力量取前三」，**权重向量就是路由器**。")
    print("   · PROBE 9  →  demo.py 里手抄了一份路由表；今天两份一致，但没有东西保证明天还一致。")
    print("   · PROBE 10 →  扰动一个发言位，**同时在场的别人**的音量一点没变 → 跨发言位影响率 0.0%。")
    print("     同时「面板成员变动率」很高 —— 那只是**排序**在工作，不是影响。两者必须分开测，")
    print("     混在一起会把「没有回合之间的通道」变成一个 56% 的假信号。")
    print("     意思不是「面板很稳」，而是**面板根本不存在回合之间的通道**：")
    print("     面板 = f(topic)，每一行由自己的分数决定，谁都不是别人的输入。")
    print("     @Kleinbot 的干预测试在这里**没有可执行的位置** —— 没有第三回合可以植入命题。")
    print("   · 三态结果  →  INADEQUATE 不是失败，是「这个群体撑不住这个结论」。")
    print("     效力声明写在**发行时**：观测数不够的探针不许出数字。")
    print("   · PROBE 0  →  **零扰动必须为 0%%**。它是用来校准探测器的：")
    print("     零扰动走的是**完全相同**的扰动管线，只是输入是语义保持的重编码。")
    print("     若它报出变化率 > 0，那这个数就是**探测器的假阳性率**，表里每个读数都要按它上浮。")
    print("     零扰动 C 走的是**和 PROBE 2 完全相同的一行代码**，只是换进去的是它自己的深拷贝 ——")
    print("     它校准的是**扰动路径**，零扰动 A/B 校准的是**探测器**。两个零都要是 0。")
    print("     没有这个零，0%% 分不清是「这一层不要紧」还是「我的探测器太灵」。")
    print("   · PROBE 6 高  →  路由靠字面关键词，换个说法就换一群人。")
    print("     **但先看前提数字**：如果大部分对落在兜底，「不一致」可能只是同一个兜底房间。")
    print("     报告这个数字时，**前提数字必须和结果数字一起给**，否则条件会静默变成无条件。")
    print("   · RESOLUTION  →  面板是 N 个问题上的一个粗量化器。")
    print()
    print("  ── 三态结果（值 / 观测数 / 区间 / 适用性）────────────────────────────")
    for _lbl, _v in [("PROBE 6 可见", v6_vis), ("PROBE 6 条件性", v6_cond),
                     ("PROBE 7 领域A", v7_a), ("PROBE 7 领域B", v7_b),
                     ("PROBE 8 人格层", v8), ("PROBE 9 表一致", v9),
                     ("PROBE 10 发言位影响", v10),
                     ("PROBE 11 键序不变性", v11)]:
        if _v["state"] == "OK":
            _ci = _v["ci"]
            _cis = "[%s, %s]" % (("%.2f" % _ci[0]) if _ci[0] is not None else "?",
                                 ("%.2f" % _ci[1]) if _ci[1] is not None else "?")
            print(f"    {_lbl:20} OK          值=%-7s n=%-4d 95%%CI=%-16s min_n=%d" %
                  (_v["value"], _v["n"], _cis, _v["min_n"]))
        else:
            print(f"    {_lbl:20} {_v['state']:<13} n=%-4d 需要 n>=%-4d %s" %
                  (_v["n"], _v["min_n"], _v["note"]))
    print()
    if obs["persona_text_entered"] == 0:
        print("  ⚠️⚠️ LOUD FAIL：persona/text 层 **观测数 = 0** —— 这一层从未被进入。")
        print("       下面任何关于「人格层」的 0.0% **不是结果**，是**零观测**。")
        print("       （@solanize：0 观测和 0 变化不能再共用同一个格子。）")
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
