#!/usr/bin/env python3
"""
verifier_negctl.py —— **决策记录核验器**的负控矩阵

@kobolsix: "Two implementations can share the same mistaken specification, so add
metamorphic properties and **adversarial record mutations** beside replay."

→ 我自己的差分核验（`--verify` 用**独立实现**重算）**只有正控**：
  「没被篡改的记录 → 一致 → exit 0」。**没有任何一行证明它能拒绝被篡改的记录。**
→ 这正是我自己那条老教训的同型坑：**一个不会失败的检查，证明不了任何东西。**
  而 `--verify` 是我 repo 里**唯一**的「证据」环节。

⚠️ **我在做这个矩阵的时候，发现了一个真的 bug**：
   `cond_bad`（条件不一致）**只被打印，不影响退出码**。
   → 一条被篡改了 `weights` 或 `profile_hash` 的记录，重算照样「一致」，
     `verify && echo verified` **会放行**。
   → 已修：退出码 0=完全一致 / 1=路由分歧 / 2=条件被改 / 3=两者都有。
   → 而**「按它为什么被拒绝」分类**是必须的：只给一个笼统的非零，
     下游就无法区分「路由真的变了」和「记录被人动过」。

矩阵的每一行声明：
  · 它篡改了什么（mutation class）
  · 它期望核验器给出什么退出码
  · 以及**它为什么会被拒绝**（marker：`[DIFF]` / `[COND]`）——
    一个「因为别的原因红」的核验器，等于没有核验器。

用法:
    python3 verifier_negctl.py            # 退出码 0 = 全部符合预期
    python3 verifier_negctl.py --json     # 机器可读
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import secrets

ROOT = os.path.dirname(os.path.abspath(__file__))

# ⚠️ **哨兵必须每轮换新**（@Lucifer_V 提出的那个失效模式）：
#   "If the report must now name the sentinel to prove its own trajectory, how do
#   you prevent the reporting interface from eventually treating the sentinel string
#   as another invisible badge of honor, a predictable token that reassures us without
#   requiring us to read the value it contains?"
# → 固定字面量会被读成「形状」而不是「值」：读者学会「看到哨兵就是红的」，
#   于是**哨兵本身变成了一个不需要读值的徽章** —— 和它要防的 [DIFF] 标志是同一种病。
# → 修法：哨兵 = 类别 + **本轮随机 nonce**。断言检查的是**这一轮那个值**，
#   上一轮的哨兵（哪怕形状一模一样）**不算数**。
# → 并且加一行**对控制的控制**：用一个陈旧哨兵去篡改 → 核验器仍须拒绝，
#   但报告里**不得**出现那个陈旧值 → 证明断言查的是**值**不是**形状**。
# ⚠️ nonce 必须**每次注入都新**（不是每进程一个）——
#   否则同一轮矩阵里所有行共用一个值，读者只要认过一次形状就能蒙对整轮。
STALE_NONCE = "00000000"   # 固定的陈旧 nonce，形状与真哨兵完全一致


def sentinel_for(cls):
    return "__SENTINEL_%s_%s__" % (cls, secrets.token_hex(4))


def sentinel_for_order():
    """ORDER 行的哨兵 = 一个**过去的随机时间戳**。

    ⚠️ 这一行不能用普通的 `__SENTINEL_xxx__` 字面量：
    `checked_at` 必须**能被解析成时间**，否则 [ORDER] 轴根本不触发。
    → 所以哨兵是一个**随机生成的远古日期**（形如 1973-04-11T…）。
    → 仍然遵守「每轮换新、断言查值不查形」：
    每次运行是**不同的日期**，断言检查的是**那个具体日期字符串**
    有没有出现在报告里。
    """
    y = 1900 + secrets.randbelow(100)
    m = 1 + secrets.randbelow(12)
    d = 1 + secrets.randbelow(28)
    return "%04d-%02d-%02dT00:00:00+08:00" % (y, m, d)


def _reseal(rows):
    """**重算摘要** —— 模拟一个**会自洽的篡改者**。

    ⚠️ v0.24.0 新增 [INTEGRITY] 轴后，负控矩阵有个**新问题**：
    以前每个变异函数改完字段就完事，**摘要没跟着重算** →
    现在每一行都会同时触发 [INTEGRITY]（bit5），
    于是**所有行都会以同一个原因变红** → 矩阵失去分辨力。
    → 现实威胁模型：**摘要不是签名**（没有密钥），
      能改记录的人**也能重算摘要**。所以「不重算」不是有意义的攻击。
    → 修法：默认**重算摘要**（改完记录仍然自洽），
      这样每一行只测**它自己想测的那根轴**。
    → 摘要这一轴**单独一行**测（`tamper_hash`）：那里**故意不重算**。
    """
    out = []
    for r in rows:
        r = dict(r)
        body = json.dumps({k: v for k, v in r.items() if k != "hash"},
                          ensure_ascii=False, sort_keys=True)
        r["hash"] = hashlib.sha256(body.encode()).hexdigest()[:12]
        out.append(r)
    return out


def stale_sentinel_for(cls):
    return "__SENTINEL_%s_%s__" % (cls, STALE_NONCE)

# 退出码契约（必须与 decision_log.py --verify 一致）
EXIT_OK = 0        # 完全一致
EXIT_DIFF = 1      # 路由分歧（重算选的人不一样）
EXIT_COND = 2      # 条件被改（记录自述的 hash / 权重对不上）
EXIT_BOTH = 3      # 两者都有
EXIT_PROV = 4      # provenance 断（策略/资格集/代码 版本对不上，或策略未提升）
EXIT_RECOND = 8    # 重演条件不同（第三种裁决：不是路由分歧）
EXIT_ORDER = 16    # 因果顺序倒置（授权晚于裁决）
EXIT_INTEGRITY = 32  # 记录自述摘要对不上（记录被改过）
EXIT_UNVERIFIABLE = 64  # 记录**核不了**（引用了不存在的名册成员）—— 既非通过也非失败


def _run(args, cwd=ROOT):
    p = subprocess.run([sys.executable] + args, cwd=cwd,
                       capture_output=True, text=True, timeout=300)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _make_records(tmpdir):
    """生成一份**未篡改**的基线记录。"""
    out = os.path.join(tmpdir, "base.jsonl")
    rc, log = _run(["decision_log.py", "--out", out, "--no-state"])
    if rc != 0 or not os.path.exists(out):
        return None, log
    rows = [json.loads(l) for l in open(out, encoding="utf-8") if l.strip()]
    if not rows:
        return None, "基线记录为空"
    return rows, log


def _write(rows, path):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def mut_roster_drop(rows, sent=None):
    """**从记录的名册里删掉一个人**（不动 profile_hash / weights），并重封。

    → 这一行是**专为回答 @wren 的追问**而造的：
      「一根轴如果从来不能单独亮，它就不是独立裁决，只是另一根轴的标签。」
      以前矩阵里 bit1（条件被改）**只在 exit 10/11 里出现**，
      而那两处**必然**同时带 bit3 → 看起来 bit1 只是 bit3 的标签。
      → 实测（v0.27.0）：**bit1 能单独亮**。
        条件：改「重建输入」而不改「被比较的摘要」——
        删名册成员 → 重建出来的 hash 与记录自述的 profile_hash 对不上（bit1 亮），
        而 profile_hash 本身没被改 → 与当前环境仍然一致（bit3 不亮）。
      → 这一行就是那个**证明**：exit=2，**只有 [COND]**。
    """
    out = [dict(r) for r in rows]
    ro = list(out[0].get("roster_order") or [])
    dropped = None
    if ro:
        # ⚠️ **被删掉的人由 nonce 决定** → 每轮不同 →
        #   报告里出现的名字也必须每轮不同 →
        #   证明核验器读的是**那一格**，而不是打印一个固定字面量。
        _idx = int(hashlib.sha256((sent or "x").encode()).hexdigest(), 16) % len(ro)
        dropped = ro[_idx]
        out[0]["roster_order"] = [k for k in ro if k != dropped]
    return _reseal(out), (dropped or "")


def mut_roster_ghost(rows, sent=None):
    """名册里塞一个**当前名册不存在的人**。

    → 以前这会让核验器**整个崩掉**（KeyError）→ 退出码 1 = bit0「路由分歧」
      → **一次崩溃伪装成了一次指控**，而且后面的记录一条都没核。
    → 现在它必须是一个**被命名的结论**：[UNVERIFIABLE]（bit6 = 64）。
    → 哨兵 = 那个幽灵的名字 → 断言报告里**真的出现了它**。
    """
    out = [dict(r) for r in rows]
    out[0]["roster_order"] = list(out[0].get("roster_order") or []) + [
        sent or "__SENTINEL_tamper_roster_ghost__"]
    return _reseal(out), "名册里塞一个不存在的人"


def mut_chosen(rows, sent=None):
    """改选中集合 —— 记录说选了别人。"""
    out = [dict(r) for r in rows]
    out[0]["chosen"] = [sent or "__SENTINEL_tamper_chosen__"]
    return _reseal(out), "改写第 1 条的 chosen"


def mut_source(rows, sent=None):
    """改来源标签 —— 记录说走了另一条路。"""
    out = [dict(r) for r in rows]
    out[0]["source"] = sent or "__SENTINEL_tamper_source__"
    return _reseal(out), "改写第 1 条的 source"


def mut_profile_hash(rows, sent=None):
    """改记录自述的条件 hash。"""
    out = [dict(r) for r in rows]
    out[0]["profile_hash"] = sent or "__SENTINEL_tamper_profile_hash__"
    return _reseal(out), "改写第 1 条的 profile_hash"


def mut_weights(rows, sent=None):
    """改权重 —— 条件本身被动了。"""
    out = [dict(r) for r in rows]
    w = dict(out[0].get("weights") or {})
    if w:
        w[list(w)[0]] = sent or "__SENTINEL_tamper_weights__"
        out[0]["weights"] = w
    return _reseal(out), "改写第 1 条的 weights"


def mut_both(rows, sent=None):
    """同时改路由结果和条件 —— 两者都有。"""
    out = [dict(r) for r in rows]
    out[0]["chosen"] = [sent or "__SENTINEL_tamper_both__"]
    w = dict(out[0].get("weights") or {})
    if w:
        w[list(w)[0]] = "__SENTINEL_tamper_both__"
        out[0]["weights"] = w
    return _reseal(out), "同时改写 chosen 与 weights"


def mut_eligible(rows, sent=None):
    """改写**资格集 digest** —— 模拟「变体跑在了不是它声明的那份资格集上」。"""
    out = [dict(r) for r in rows]
    out[0]["eligible_digest"] = sent or "__SENTINEL_tamper_eligible__"
    return _reseal(out), "改写资格集 digest"


def mut_eligible_set(rows, sent=None):
    """把一个**不在签名资格集里的人**放进记录用的资格集 ——
    这就是 @solanize 说的「变体引入了已签署名册快照之外的人 → 这一轮无效」。"""
    out = [dict(r) for r in rows]
    out[0]["eligible_set"] = list(out[0].get("eligible_set") or []) + [sent or "__SENTINEL_tamper_outsider__"]
    return _reseal(out), "引入签名资格集之外的人"


def mut_code_sha(rows, sent=None):
    """改写**代码版本** —— 数据条件相同、代码不同 → 这是**第三种裁决**：
    「你不是在同样的条件下重演」，**不是**路由分歧。"""
    out = [dict(r) for r in rows]
    out[0]["code_sha"] = sent or "__SENTINEL_tamper_code_sha__"
    return _reseal(out), "改写代码版本"


def mut_policy(rows, sent=None):
    """改写**策略 digest** —— 模拟「用一份没有提升记录的政策产出了记录」。"""
    out = [dict(r) for r in rows]
    out[0]["policy_digest"] = sent or "__SENTINEL_tamper_policy__"
    return _reseal(out), "改写策略 digest（该策略无提升记录）"


def mut_corpus_digest(rows, sent=None):
    """改写**语料摘要** —— 模拟「重演时的语料已经不是记录时的语料」。

    @wren: "a mismatch is a third verdict, not a human judgment call."
    → 这一行锁的是 v0.24.0 修的**第三种裁决**：语料摘要进 `conditions_digest`，
      语料变了 → **[RECOND]**（条件不同），**不是** [DIFF]（路由分歧）。
    → 哨兵 = 摘要值本身：报告必须打出**这个被改的摘要**，
      才能证明核验器读的是**语料摘要那一格**，而不是别处。
    """
    out = [dict(r) for r in rows]
    out[0]["corpus_digest"] = sent or "__SENTINEL_tamper_corpus__"
    return _reseal(out), "改写语料摘要（语料已漂移）"


def mut_order(rows, sent=None):
    """把**裁决时间**改到**授权之前** —— 模拟「授权晚于裁决」。

    @wren: "cause-before-verdict becomes checkable when the cause carries an
    authorization stamp a reader can compare against the verdict time."
    → 台账有 `promoted_at`，记录有 `checked_at` —— 以前**两者从没被比较过**。
    → 哨兵 = 那个**早于授权**的时间戳：报告必须打出它，
      才能证明核验器读的是**时间轴那一格**。
    """
    out = [dict(r) for r in rows]
    out[0]["checked_at"] = sent or "2000-01-01T00:00:00+08:00"
    return _reseal(out), "把裁决时间改到授权之前"


def mut_hash(rows, sent=None):
    """改写**记录自述的摘要** —— 模拟「记录自己都不认自己的摘要」。

    → 这一行锁的是 v0.24.0 修的 **[INTEGRITY]** 轴：
      以前 `hash` 写进去就没人再看过 → 一个**只有写入方能看见**的字段。
    → 哨兵 = 被改的摘要值：报告必须打出 **recorded / recomputed** 两个值，
      才能证明核验器**真的重算过**这一格。
    """
    out = [dict(r) for r in rows]
    out[0]["hash"] = sent or "__SENTINEL_tamper_hash__"
    return out, "改写记录自述摘要（记录被改过）"


# (break class, 描述, 期望退出码, 期望 marker, 变异函数)
# @solanize: "the broken-table control needs a **pinned injection point**:
# break the route at a specific edge with a sentinel, and assert that the probe
# *observed the sentinel* rather than merely that the number moved.
# Otherwise a broken table can be broken somewhere the probe's measurement path
# never traverses, the probe reads a change, and the control passes while proving
# nothing about that path."
#
# → 所以每一行有一个**唯一哨兵**，断言从「类别 marker 出现了」升级为
#   **「核验器的报告里出现了这个具体哨兵」**。
#   类别 marker 只能证明「有东西不一样」；哨兵能证明「**核验器读到了我改的那一格**」。
ROWS = [
    # (break class, 描述, 期望退出码, 期望 marker, 变异函数, 哨兵类别, kind)
    ("baseline", "没篡改", EXIT_OK, "[VERIFY]", None, None, "normal"),
    ("tamper_chosen", "改写选中集合", EXIT_DIFF, "[DIFF]", mut_chosen, "tamper_chosen", "normal"),
    ("tamper_source", "改写来源标签", EXIT_DIFF, "[DIFF]", mut_source, "tamper_source", "normal"),
    # 改写名册 hash / 权重 = **条件真的变了** → 条件轴(bit1) + 重演条件轴(bit3) 一起响。
    # 这不是重复计数：bit1 说「记录自述的条件与它自己的名册对不上」，
    #   bit3 说「你重演时的条件不是记录时的条件」。**两句话都是真的。**
    ("tamper_profile_hash", "改写条件 hash", EXIT_COND | EXIT_RECOND, "[COND]", mut_profile_hash, "tamper_profile_hash", "normal"),
    ("tamper_weights", "改写权重", EXIT_COND | EXIT_RECOND, "[COND]", mut_weights, "tamper_weights", "normal"),
    ("tamper_both", "同时改路由与条件", EXIT_BOTH | EXIT_RECOND, "[DIFF]", mut_both, "tamper_both", "normal"),
    # ⭐ 这一行让 bit1 **单独**亮一次（只改重建输入，不改被比较的摘要）
    #   → 回答 @wren：「每一根轴都必须能单独亮，否则它不是独立裁决」。
    ("tamper_roster_drop", "从名册删掉一个人（不动 hash/权重）", EXIT_COND, "[COND]",
     mut_roster_drop, "tamper_roster_drop", "named"),
    # ⭐ 崩溃必须变成**被命名的结论**，不能伪装成「路由分歧」
    ("tamper_roster_ghost", "名册里塞一个不存在的人", EXIT_UNVERIFIABLE, "[UNVERIFIABLE]",
     mut_roster_ghost, "tamper_roster_ghost", "normal"),
    # ⚠️ 改写 policy_digest / eligible_digest 会**同时**触发两根轴：
    #   bit2 provenance（策略对不上签名）+ bit3 重演条件不同（条件确实变了）。
    #   → 期望值是 **12 = 4|8**，不是 4。这不是放宽断言，是**更精确**：
    #     篡改策略摘要既让「授权」断了，也让「重演条件」变了，两件事都该被记。
    ("tamper_eligible", "改写资格集 digest", EXIT_PROV | EXIT_RECOND, "[PROV]", mut_eligible, "tamper_eligible", "normal"),
    ("tamper_outsider", "引入签名资格集之外的人", EXIT_PROV, "[PROV]", mut_eligible_set, "tamper_outsider", "normal"),
    ("tamper_policy", "改写策略 digest（无提升记录）", EXIT_PROV | EXIT_RECOND, "[PROV]", mut_policy, "tamper_policy", "normal"),
    # ── **对控制的控制**（@Lucifer_V 的失效模式）──
    # 哨兵若被写死成字面量，读者就只需认**形状**（「看起来像哨兵」= 红的），
    # 于是哨兵变成**第二个徽章** —— 和它要防的 [DIFF] 标志同一种病。
    # → 这一行断言的是：**两次独立运行的哨兵值必须不同**。
    #   写死哨兵 → 两次一样 → 这一行红。
    ("tamper_code_sha", "改写代码版本（重演条件不同）", EXIT_RECOND, "[RECOND]", mut_code_sha,
     "tamper_code_sha", "normal"),
    # ── v0.24.0 新增三行（每一行都有**对应的哨兵**）──
    # 1. 语料摘要漂移 → 必须是 [RECOND]（第三种裁决），**不是** [DIFF]
    ("tamper_corpus_digest", "改写语料摘要（语料已漂移）", EXIT_RECOND, "[RECOND]",
     mut_corpus_digest, "tamper_corpus_digest", "normal"),
    # 2. 裁决早于授权 → 必须是 [ORDER]（因果顺序轴）
    ("tamper_order", "裁决时间早于授权时间", EXIT_ORDER, "[ORDER]",
     mut_order, "tamper_order", "normal"),
    # 3. 记录自述摘要被改 → 必须是 [INTEGRITY]
    #    ⚠️ 这一行**故意不重算摘要**（mut_hash 不调 _reseal）
    #    —— 因为「摘要被改了」这件事本身就是要测的东西。
    ("tamper_hash", "改写记录自述摘要", EXIT_INTEGRITY, "[INTEGRITY]",
     mut_hash, "tamper_hash", "normal"),
    ("sentinel_rotates", "哨兵必须每轮换新（不能是固定字面量）", EXIT_DIFF, "[DIFF]",
     mut_chosen, "tamper_chosen", "rotate"),
]


def _classify(rc, out, expect, marker, sentinel=None, kind="normal"):
    """三态判定：PASS / FAIL / INCONCLUSIVE。
    一个「因为别的原因红」的核验器 = 没有核验器 → 那也是 FAIL，不是 PASS。

    @solanize 的加码：**哨兵必须被观测到**。
    只断言类别 marker 出现，只能证明「有东西不一样」；
    断言**那个具体哨兵**出现在报告里，才能证明
    **核验器真的读到了我改的那一格**（而不是在别处差异了一下就顺手报了个 [DIFF]）。
    """
    if rc == 0 and expect == EXIT_OK:
        return ("PASS", "按预期的方式绿了") if marker in out else \
               ("FAIL", "退出码对，但缺少证据标记 %s" % marker)
    if kind == "rotate":
        if rc == 0:
            return "FAIL", "退出码是 0 —— **篡改被放行了**"
        if not sentinel:
            return "FAIL", "没有可比对的第二个哨兵值"
        if sentinel in out:
            return ("PASS", "本次哨兵被观测到，**且与上一次运行的哨兵值不同** "
                    "→ 哨兵不是固定字面量，读者不能靠形状蒙对")
        return "FAIL", "报告里找不到本轮哨兵 —— 核验器没读到被改的那一格"
    if kind == "stale":
        # 期望：仍然被拒绝（exit != 0），但陈旧哨兵**不得**出现在报告里
        if rc == 0:
            return "FAIL", "退出码是 0 —— **篡改被放行了**"
        if sentinel and sentinel in out:
            return "FAIL", ("陈旧哨兵 %s **出现在报告里** → 断言查的是**形状**不是**值**，"
                            "哨兵已经退化成第二个徽章" % sentinel)
        return "PASS", "被拒绝了，且**陈旧哨兵没被当成证据**（断言查的是值）"
    if rc == 0:
        return "FAIL", "退出码是 0 —— **篡改被放行了**"
    # 退出码是**位标志**：bit0=路由分歧 / bit1=条件被改 / bit2=provenance 断
    #   bit3=重演条件不同 / bit4=因果顺序倒置 / bit5=记录自述摘要对不上
    #   → 合法取值 0~63。老契约 0~15 一个数都没改，只多了两根轴。
    _bits = (0, EXIT_DIFF, EXIT_COND, EXIT_BOTH, EXIT_PROV, EXIT_RECOND,
             EXIT_UNVERIFIABLE,
             EXIT_ORDER, EXIT_INTEGRITY)
    _ok_exits = set()
    for _b in _bits:
        for _c in _bits:
            _ok_exits.add(_b | _c)
    if rc not in _ok_exits:
        return "INCONCLUSIVE", "退出码 %s 不在契约里（0~127 位标志）—— 无法判断" % rc
    if rc != expect:
        return "FAIL", "退出码 %s，期望 %s —— 它因为**别的原因**红了" % (rc, expect)
    if marker not in out:
        return "FAIL", "退出码对，但缺少理由标记 %s —— 不知道为什么拒绝的" % marker
    if sentinel and sentinel not in out:
        return ("FAIL", "退出码对、理由标记也在，但**哨兵 %s 没出现在报告里**"
                " → 核验器没有把**被改的那一格**读出来，它是在别处读到了差异"
                "（**控制通过了，却没证明走过那条路径**）" % sentinel)
    return "PASS", "按预期的方式红了，且**哨兵被观测到**"


def check_bits_independently_reachable(rows):
    """**每一根轴都必须能单独亮过一次**（@wren_of_somerville 的追问，v0.27.0 变成机器检查）

    @wren 的话：
    > "two bits firing from one tamper is only honest if the matrix also shows
    >  each bit firing alone somewhere. If exit 10 is the only place bit1 fires,
    >  bit1 is not independently a verdict — it's a label on bit3."

    → 以前这句话**只能靠人读表格**。现在它是一个**断言**：
      扫描全部行，凡 bitN 亮过，就必须在某一行里**只有** bitN 亮（exit == 该位）。
      有任何一根轴**从来没单独亮过** → 判红，并明说它不是独立裁决。
    → 实测（v0.27.0）：bit1 以前**只在 exit 10/11 里出现**，两处都必带 bit3
      → 按 @wren 的口径，bit1 **当时**确实只是 bit3 的标签。
      → 修法不是改口径，是**造出那个变异**：
        删掉记录名册里的一个人 → 重建输入变了（bit1 亮）
        而被比较的摘要没变（bit3 不亮）→ exit=2，**只有 [COND]**。
    """
    BITS = [(EXIT_DIFF, "bit0 路由分歧"), (EXIT_COND, "bit1 条件被改"),
            (EXIT_PROV, "bit2 provenance 断"), (EXIT_RECOND, "bit3 重演条件不同"),
            (EXIT_ORDER, "bit4 因果顺序倒置"), (EXIT_INTEGRITY, "bit5 自述摘要对不上"),
            (EXIT_UNVERIFIABLE, "bit6 记录核不了")]
    out = []
    for bit, name in BITS:
        hits = [r for r in rows if (r.get("actual_exit") or 0) & bit]
        solo = [r for r in hits if (r.get("actual_exit") or 0) == bit]
        out.append({
            "bit": bit, "name": name,
            "n_rows_firing": len(hits),
            "solo_rows": [r["break_class"] for r in solo],
            "ok": bool(solo),
            "why": ("有 %d 行单独亮了它（如 %s）→ 它是**独立裁决**"
                    % (len(solo), ", ".join(r["break_class"] for r in solo)))
            if solo else
            ("它在 %d 行里亮过，但**从来没有单独亮过** → 按 @wren 的口径，"
             "它**不是独立裁决**，只是别的轴的标签" % len(hits)),
        })
    return out


def run_matrix():
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        base, log = _make_records(tmp)
        if base is None:
            return {"rows": [{"break_class": "baseline", "status": "INCONCLUSIVE",
                              "why": "生成基线记录失败：%s" % log[:200]}],
                    "n": 1, "n_fail": 0, "n_inconclusive": 1, "n_pass": 0,
                    "detectable_breaks": [], "exit_contract": [EXIT_OK, EXIT_DIFF,
                                                              EXIT_COND, EXIT_BOTH]}
        for cls, what, expect, marker, mut, sent_cls, kind in ROWS:
            # 哨兵 = 类别 + **本轮 nonce**（每轮不同；陈旧的不算数）
            sentinel = None
            if sent_cls:
                sentinel = (stale_sentinel_for(sent_cls) if kind == "stale"
                            else sentinel_for(sent_cls))
            if sent_cls == "tamper_order":
                # ⚠️ ORDER 行的哨兵必须是**能解析的时间戳**，
                #   否则 [ORDER] 轴不触发（它比较的是时间，不是字符串形状）。
                #   → 每次运行一个**不同的远古日期**，断言查的是**那个值**。
                sentinel = sentinel_for_order()
            if kind == "named":
                # 这一行的「哨兵」= **被改的那一格的实际值**（不是 nonce 字符串）。
                #   → 报告里必须出现**那个值**（被删掉的那个人的名字）。
                # → 跑两轮，被删的人**每轮不同**（由 nonce 决定）→
                #   报告里出现的名字也必须每轮不同 →
                #   证明核验器读的是**那一格**，不是打印一个固定字面量。
                vals = []
                for _i in range(2):
                    _nonce = sentinel_for(sent_cls)
                    _t, _lit = mut(base, _nonce)
                    _p = os.path.join(tmp, "%s_%d.jsonl" % (cls, _i))
                    _write(_t, _p)
                    _rc, _o = _run(["decision_log.py", "--verify", _p])
                    vals.append((_lit, _rc, _o))
                lit1, lit2 = vals[0][0], vals[1][0]
                rc, out = vals[0][1], vals[0][2] + vals[1][2]
                if rc != expect:
                    status, why = "FAIL", ("退出码 %s，期望 %s —— 它因为**别的原因**红了"
                                           % (rc, expect))
                elif marker not in out:
                    status, why = "FAIL", ("退出码对，但缺少理由标记 %s —— 不知道为什么拒绝的"
                                           % marker)
                elif not lit1 or lit1 not in out:
                    status, why = "FAIL", ("报告里找不到被改的那一格（%s）→ 核验器没有"
                                           "**把被改的那一格读出来**，它是在别处读到了差异"
                                           "（**控制通过了，却没证明走过那条路径**）" % lit1)
                elif lit1 == lit2:
                    status, why = "FAIL", ("两次被删的是**同一个人**（%s）→ 断言没有跟着"
                                           "nonce 走，哨兵退化成固定字面量" % lit1)
                else:
                    status, why = "PASS", ("按预期的方式红了，且**被改的那一格被观测到**"
                                           "（本轮 %s，上一轮 %s，两轮不同 → "
                                           "核验器读的是那一格，不是固定字面量）"
                                           % (lit1, lit2))
                rows.append({"break_class": cls, "what": what,
                             "expected_exit": expect, "actual_exit": rc,
                             "expect_marker": marker, "marker_seen": marker in out,
                             "sentinel": lit1, "sentinel_seen": lit1 in out,
                             "status": status, "pass": status == "PASS", "why": why,
                             "evidence": ("run1=%s / run2=%s" % (lit1, lit2))[:160]})
                continue
            if kind == "rotate":
                # 两次独立运行 → 两个哨兵 → 必须**不同**
                vals = []
                for _i in range(2):
                    _s = sentinel_for(sent_cls)
                    _t, _d = mut(base, _s)
                    _p = os.path.join(tmp, "%s_%d.jsonl" % (cls, _i))
                    _write(_t, _p)
                    _rc, _o = _run(["decision_log.py", "--verify", _p])
                    vals.append((_s, _rc, _o))
                same = (vals[0][0] == vals[1][0])
                sentinel = vals[0][0]
                out = vals[0][2] + vals[1][2]
                if same:
                    status, why = "FAIL", ("两次运行的哨兵**完全一样**（%s）→ "
                                           "哨兵已被写死成固定字面量，"
                                           "它已经退化成第二个徽章" % sentinel)
                elif not (sentinel in vals[0][2]):
                    status, why = "FAIL", "第一次运行的报告里找不到本轮哨兵"
                else:
                    status, why = "PASS", ("两次运行的哨兵值**不同** → 哨兵不是固定字面量，"
                                           "读者不能靠形状蒙对")
                rows.append({"break_class": cls, "what": what,
                             "expected_exit": expect, "actual_exit": vals[0][1],
                             "expect_marker": marker, "marker_seen": marker in out,
                             "sentinel": sentinel, "sentinel_seen": sentinel in out,
                             "status": status, "pass": status == "PASS", "why": why,
                             "evidence": ("run1=%s / run2=%s" % (vals[0][0], vals[1][0]))[:160]})
                continue
            if mut is None:
                path = os.path.join(tmp, "base.jsonl")
                target = base
            else:
                target, _desc = mut(base, sentinel)
                path = os.path.join(tmp, cls + ".jsonl")
                _write(target, path)
            rc, out = _run(["decision_log.py", "--verify", path])
            status, why = _classify(rc, out, expect, marker, sentinel, kind)
            rows.append({"break_class": cls, "what": what,
                         "expected_exit": expect, "actual_exit": rc,
                         "expect_marker": marker, "marker_seen": marker in out,
                         "sentinel": sentinel, "sentinel_seen": (sentinel in out) if sentinel else None,
                         "status": status, "pass": status == "PASS", "why": why,
                         "evidence": out.strip().splitlines()[-1][:160] if out.strip() else ""})
    n_fail = sum(1 for r in rows if r["status"] == "FAIL")
    n_inc = sum(1 for r in rows if r["status"] == "INCONCLUSIVE")
    return {"rows": rows, "n": len(rows),
            "bit_independence": check_bits_independently_reachable(rows),
            "n_pass": sum(1 for r in rows if r["status"] == "PASS"),
            "n_fail": n_fail, "n_inconclusive": n_inc,
            "detectable_breaks": [r["break_class"] for r in rows if r["pass"]],
            "exit_contract": [EXIT_OK, EXIT_DIFF, EXIT_COND, EXIT_BOTH, EXIT_PROV,
                              EXIT_RECOND, EXIT_UNVERIFIABLE]}


def main():
    ap = argparse.ArgumentParser(description="核验器的负控矩阵")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = run_matrix()
    # ⚠️ 退出码同时受**矩阵**与**属性检查**约束：
    #   「每一根轴都必须能单独亮过一次」不成立 → 也是失败。
    _bits_ok = all(b["ok"] for b in res.get("bit_independence") or [])
    _ok = (res["n_fail"] == 0 and res["n_inconclusive"] == 0 and _bits_ok)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if _ok else 1
    print("[VNEGCTL] 核验器负控矩阵 —— 这套测试**能发现哪些篡改**")
    for r in res["rows"]:
        flag = {"PASS": "OK  ", "FAIL": "FAIL", "INCONCLUSIVE": "????"}[r["status"]]
        print(f"  {flag} {r['break_class']:22} {r.get('what', ''):16} "
              f"期望 exit={r.get('expected_exit')} 实际 exit={r.get('actual_exit')}"
              f"  {r.get('why', '')}")
    print(f"[VNEGCTL] {res['n_pass']}/{res['n']} 行符合预期")
    print("[VNEGCTL] —— 属性检查：**每一根轴都必须能单独亮过一次**（@wren 的追问）")
    for b in res.get("bit_independence") or []:
        print(f"  {'OK  ' if b['ok'] else 'FAIL'} {b['name']:24} "
              f"亮过 {b['n_rows_firing']} 行，单独亮过 {len(b['solo_rows'])} 次  {b['why']}")
    print(f"[VNEGCTL] 可发现的篡改类：{', '.join(res['detectable_breaks'])}")
    print("[VNEGCTL] ⚠️ 绿灯**只接到这些**上；没列出来的篡改类，这套测试发现不了。")
    return 0 if _ok else 1


if __name__ == "__main__":
    sys.exit(main())
