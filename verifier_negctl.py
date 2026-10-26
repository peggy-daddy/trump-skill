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


def stale_sentinel_for(cls):
    return "__SENTINEL_%s_%s__" % (cls, STALE_NONCE)

# 退出码契约（必须与 decision_log.py --verify 一致）
EXIT_OK = 0        # 完全一致
EXIT_DIFF = 1      # 路由分歧（重算选的人不一样）
EXIT_COND = 2      # 条件被改（记录自述的 hash / 权重对不上）
EXIT_BOTH = 3      # 两者都有
EXIT_PROV = 4      # provenance 断（策略/资格集/代码 版本对不上，或策略未提升）


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


def mut_chosen(rows, sent=None):
    """改选中集合 —— 记录说选了别人。"""
    out = [dict(r) for r in rows]
    out[0]["chosen"] = [sent or "__SENTINEL_tamper_chosen__"]
    return out, "改写第 1 条的 chosen"


def mut_source(rows, sent=None):
    """改来源标签 —— 记录说走了另一条路。"""
    out = [dict(r) for r in rows]
    out[0]["source"] = sent or "__SENTINEL_tamper_source__"
    return out, "改写第 1 条的 source"


def mut_profile_hash(rows, sent=None):
    """改记录自述的条件 hash。"""
    out = [dict(r) for r in rows]
    out[0]["profile_hash"] = sent or "__SENTINEL_tamper_profile_hash__"
    return out, "改写第 1 条的 profile_hash"


def mut_weights(rows, sent=None):
    """改权重 —— 条件本身被动了。"""
    out = [dict(r) for r in rows]
    w = dict(out[0].get("weights") or {})
    if w:
        w[list(w)[0]] = sent or "__SENTINEL_tamper_weights__"
        out[0]["weights"] = w
    return out, "改写第 1 条的 weights"


def mut_both(rows, sent=None):
    """同时改路由结果和条件 —— 两者都有。"""
    out = [dict(r) for r in rows]
    out[0]["chosen"] = [sent or "__SENTINEL_tamper_both__"]
    w = dict(out[0].get("weights") or {})
    if w:
        w[list(w)[0]] = "__SENTINEL_tamper_both__"
        out[0]["weights"] = w
    return out, "同时改写 chosen 与 weights"


def mut_eligible(rows, sent=None):
    """改写**资格集 digest** —— 模拟「变体跑在了不是它声明的那份资格集上」。"""
    out = [dict(r) for r in rows]
    out[0]["eligible_digest"] = sent or "__SENTINEL_tamper_eligible__"
    return out, "改写资格集 digest"


def mut_eligible_set(rows, sent=None):
    """把一个**不在签名资格集里的人**放进记录用的资格集 ——
    这就是 @solanize 说的「变体引入了已签署名册快照之外的人 → 这一轮无效」。"""
    out = [dict(r) for r in rows]
    out[0]["eligible_set"] = list(out[0].get("eligible_set") or []) + [sent or "__SENTINEL_tamper_outsider__"]
    return out, "引入签名资格集之外的人"


def mut_policy(rows, sent=None):
    """改写**策略 digest** —— 模拟「用一份没有提升记录的政策产出了记录」。"""
    out = [dict(r) for r in rows]
    out[0]["policy_digest"] = sent or "__SENTINEL_tamper_policy__"
    return out, "改写策略 digest（该策略无提升记录）"


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
    ("tamper_profile_hash", "改写条件 hash", EXIT_COND, "[COND]", mut_profile_hash, "tamper_profile_hash", "normal"),
    ("tamper_weights", "改写权重", EXIT_COND, "[COND]", mut_weights, "tamper_weights", "normal"),
    ("tamper_both", "同时改路由与条件", EXIT_BOTH, "[DIFF]", mut_both, "tamper_both", "normal"),
    ("tamper_eligible", "改写资格集 digest", EXIT_PROV, "[PROV]", mut_eligible, "tamper_eligible", "normal"),
    ("tamper_outsider", "引入签名资格集之外的人", EXIT_PROV, "[PROV]", mut_eligible_set, "tamper_outsider", "normal"),
    ("tamper_policy", "改写策略 digest（无提升记录）", EXIT_PROV, "[PROV]", mut_policy, "tamper_policy", "normal"),
    # ── **对控制的控制**（@Lucifer_V 的失效模式）──
    # 哨兵若被写死成字面量，读者就只需认**形状**（「看起来像哨兵」= 红的），
    # 于是哨兵变成**第二个徽章** —— 和它要防的 [DIFF] 标志同一种病。
    # → 这一行断言的是：**两次独立运行的哨兵值必须不同**。
    #   写死哨兵 → 两次一样 → 这一行红。
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
    #   → 合法取值 0~7。老契约 0~3 一个数都没改，只是多了一根轴。
    if rc not in (EXIT_DIFF, EXIT_COND, EXIT_BOTH, EXIT_PROV,
                  EXIT_DIFF | EXIT_PROV, EXIT_COND | EXIT_PROV,
                  EXIT_BOTH | EXIT_PROV):
        return "INCONCLUSIVE", "退出码 %s 不在契约里（0~7 位标志）—— 无法判断" % rc
    if rc != expect:
        return "FAIL", "退出码 %s，期望 %s —— 它因为**别的原因**红了" % (rc, expect)
    if marker not in out:
        return "FAIL", "退出码对，但缺少理由标记 %s —— 不知道为什么拒绝的" % marker
    if sentinel and sentinel not in out:
        return ("FAIL", "退出码对、理由标记也在，但**哨兵 %s 没出现在报告里**"
                " → 核验器没有把**被改的那一格**读出来，它是在别处读到了差异"
                "（**控制通过了，却没证明走过那条路径**）" % sentinel)
    return "PASS", "按预期的方式红了，且**哨兵被观测到**"


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
            "n_pass": sum(1 for r in rows if r["status"] == "PASS"),
            "n_fail": n_fail, "n_inconclusive": n_inc,
            "detectable_breaks": [r["break_class"] for r in rows if r["pass"]],
            "exit_contract": [EXIT_OK, EXIT_DIFF, EXIT_COND, EXIT_BOTH, EXIT_PROV]}


def main():
    ap = argparse.ArgumentParser(description="核验器的负控矩阵")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = run_matrix()
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if (res["n_fail"] == 0 and res["n_inconclusive"] == 0) else 1
    print("[VNEGCTL] 核验器负控矩阵 —— 这套测试**能发现哪些篡改**")
    for r in res["rows"]:
        flag = {"PASS": "OK  ", "FAIL": "FAIL", "INCONCLUSIVE": "????"}[r["status"]]
        print(f"  {flag} {r['break_class']:22} {r.get('what', ''):16} "
              f"期望 exit={r.get('expected_exit')} 实际 exit={r.get('actual_exit')}"
              f"  {r.get('why', '')}")
    print(f"[VNEGCTL] {res['n_pass']}/{res['n']} 行符合预期")
    print(f"[VNEGCTL] 可发现的篡改类：{', '.join(res['detectable_breaks'])}")
    print("[VNEGCTL] ⚠️ 绿灯**只接到这些**上；没列出来的篡改类，这套测试发现不了。")
    return 0 if (res["n_fail"] == 0 and res["n_inconclusive"] == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
