#!/usr/bin/env python3
"""
condition_sensitivity.py —— **逐字段问：「改了它，裁决会变吗？」**（v0.28.0）

## 为什么有这个脚本（@wren_of_somerville 的追问）

@wren 在 39cef505 里说：

> "the inventory check is your own seed confession run in both directions.
>  For every field, ask 'would changing this change the verdict?'
>  Fields that change the verdict but aren't in the set are **drift-blindness**;
>  fields in the set that change nothing are **false alarms that train readers
>  to ignore the axis** — seed was the second case, and excluding it was correct.
>  Run that test per-field and the inventory stops being judgment call."

→ 以前「哪些字段算重演条件」是**我手工列的清单** = 判断题。
→ 现在它变成**逐字段实测**：改一个字段 → 重跑核验器 → 看**裁决**变没变。
   变 = 承载（load-bearing）；不变 = 中性（inert）。

## 两种缺陷，一次测出来

| 症状 | 含义 | 修法 |
|------|------|------|
| **drift-blindness** | 改了它**裁决会变**，但它**不在**条件集里 | 把字段**加进**条件集 |
| **false alarm** | 它**在**条件集里，但改了它**裁决不变** | 把字段**移出**条件集 |

→ 这就是 @wren 说的「清单不再是判断题」。
→ **注意**：这个脚本测的是**核验器的裁决**，不是「这个字段重要不重要」。
   一个字段可以很重要但不影响裁决（例如 `topic` 是叙事，不是条件）。

用法:
    python3 condition_sensitivity.py            # 人类可读
    python3 condition_sensitivity.py --json     # 机器可读
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

# 核验器**当前**认定的那一组「重演条件」（对照用）
CONDITION_SET = ["profile_hash", "weights", "policy_digest",
                 "eligible_digest", "corpus_digest", "code_sha"]

# ---- **豁免表**（waiver registry）--------------------------------------------
# @wren: "the waiver needs evidence, the verdict stays by default.
#  Name it in the README as a rule, not a mechanism."
# → 所以「改了会变但不在条件集里」的字段**不能默默放行**：
#   它要么有一条**具名**的豁免理由（在这里，且在 README 里同名），
#   要么这个脚本**判红**。
WAIVERS = {
    "topic": "它是**问题**，不是条件：改它 = 问另一件事 → 裁决当然不同。"
             "把它算成漂移，会把所有提问都算成漂移。",
    "roster_order": "它**被 profile_hash 罩住**（profile_hash 就是「名册+权重」的摘要）："
                    "改了名册而不改摘要 → bit1 亮；改了名册**并且**改了摘要 → bit3 亮。"
                    "两头都抓得到 → 没必要再加进条件集（否则同一个事实被算两次）。",
}

# 被 @wren 点名的「种子告解」字段：seed 曾经留在清单里，
# 但它**没有任何读者** → 改了它裁决不变 → 是 false alarm。
CANDIDATE_OUTSIDE = ["seed", "tie_break", "cutoff", "route_fired",
                      "considered_causes", "topic", "production_reason"]


def _run(args, cwd=ROOT):
    p = subprocess.run([sys.executable] + args, cwd=cwd,
                       capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _reseal(rows):
    """**重算自述摘要** —— 现实威胁模型：能改记录的人也能重算摘要。"""
    out = []
    for r in rows:
        r = dict(r)
        body = json.dumps({k: v for k, v in r.items() if k != "hash"},
                          ensure_ascii=False, sort_keys=True)
        r["hash"] = hashlib.sha256(body.encode()).hexdigest()[:12]
        out.append(r)
    return out


def _make_baseline(tmp):
    out = os.path.join(tmp, "base.jsonl")
    rc, log = _run(["decision_log.py", "--out", out, "--no-state"])
    if rc != 0 or not os.path.exists(out):
        return None, log
    rows = [json.loads(l) for l in open(out, encoding="utf-8") if l.strip()]
    return (rows or None), log


def _mutate(rows, field, value):
    out = [dict(r) for r in rows]
    out[0][field] = value
    return _reseal(out)


def _mutate_drop_roster(rows):
    out = [dict(r) for r in rows]
    ro = list(out[0].get("roster_order") or [])
    if ro:
        gods = json.load(open(os.path.join(ROOT, "data", "trump-profile.json"),
                              encoding="utf-8"))["tenGods"]
        lowest = min(ro, key=lambda k: gods.get(k, {}).get("score", 0))
        out[0]["roster_order"] = [k for k in ro if k != lowest]
    return _reseal(out)


def _probes(rows):
    """每个字段一个**探针**：改它 → 看裁决变不变。"""
    r0 = rows[0]
    w = dict(r0.get("weights") or {})
    if w:
        k0 = sorted(w)[0]
        w2 = dict(w)
        w2[k0] = (w[k0] or 0) + 1
    else:
        k0, w2 = None, {}
    out = []
    for f in CONDITION_SET:
        if f == "weights":
            v = w2
        elif f in ("profile_hash", "policy_digest", "eligible_digest",
                   "corpus_digest", "code_sha"):
            v = "__SENTINEL_%s__" % f
        else:
            v = "__SENTINEL_%s__" % f
        # ⚠️ **必须把 f 也绑成默认参数**（v0.28.0 当场踩到的坑）：
        #   只绑 v 的话，f 是**闭包里的自由变量** → 所有 lambda 在**调用时**
        #   看到的都是**最后一次循环**的 f → **所有探针其实改的是同一个字段**。
        #   → 症状：整张表全是「改了不变」，只有一个探针（函数式的那个）是准的。
        #   → 这和「探针复述了被测对象」是同一族错误：**探针没有真的测它声称测的东西**。
        out.append((f, "in_set", lambda rows, v=v, f=f: _mutate(rows, f, v)))
    for f in CANDIDATE_OUTSIDE:
        if f in ("tie_break", "cutoff", "seed"):
            _cur = r0.get(f)
            # 值可能是 str / int / None -> **按类型选一个合法的新值**
            if isinstance(_cur, bool) or _cur is None:
                v = "__SENTINEL_%s__" % f
            elif isinstance(_cur, int):
                v = _cur + 1
            elif isinstance(_cur, float):
                v = _cur + 1.0
            else:
                v = "%s__SENTINEL__" % _cur
            out.append((f, "candidate", lambda rows, v=v, f=f: _mutate(rows, f, v)))
        elif f == "considered_causes":
            v = list(r0.get(f) or [])
            v = v + [{"route": "__SENTINEL_route__", "hits": 0}]
            out.append((f, "candidate", lambda rows, v=v, f=f: _mutate(rows, f, v)))
        elif f == "route_fired":
            v = "__SENTINEL_route__"
            out.append((f, "candidate", lambda rows, v=v, f=f: _mutate(rows, f, v)))
        elif f == "production_reason":
            v = "__SENTINEL_reason__"
            out.append((f, "candidate", lambda rows, v=v, f=f: _mutate(rows, f, v)))
        else:
            v = "__SENTINEL_%s__" % f
            out.append((f, "candidate", lambda rows, v=v, f=f: _mutate(rows, f, v)))
    # 名册：唯一能让 bit1 单独亮的那一格
    out.append(("roster_order", "candidate", _mutate_drop_roster))
    return out


AXIS = {"[DIFF]": 1, "[COND]": 2, "[PROV]": 4, "[RECOND]": 8,
        "[ORDER]": 16, "[INTEGRITY]": 32, "[UNVERIFIABLE]": 64}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        base, log = _make_baseline(tmp)
        if not base:
            print("生成基线记录失败：", log[:300])
            return 1
        bpath = os.path.join(tmp, "b.jsonl")
        with open(bpath, "w", encoding="utf-8") as f:
            for r in base:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        b_rc, b_out = _run(["decision_log.py", "--verify", bpath])
        if b_rc != 0:
            print("基线本身不是 exit 0（%s）→ 这次实测的前提不成立，先修基线" % b_rc)
            print(b_out[-800:])
            return 1
        results = []
        for field, where, mut in _probes(base):
            target = mut(base)
            p = os.path.join(tmp, "m.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                for r in target:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            rc, out = _run(["decision_log.py", "--verify", p])
            axes = [k for k in AXIS if k in out]
            changed = (rc != b_rc)
            in_set = field in CONDITION_SET
            waived = False
            if changed and not in_set:
                if field in WAIVERS:
                    verdict = "drift-blindness（但**有具名豁免**：%s）" % WAIVERS[field]
                    waived = True
                else:
                    verdict = "drift-blindness（改了会变，但不在条件集里，**且没有具名豁免**）"
                    waived = False
            elif in_set and not changed:
                verdict = "false alarm（在条件集里，但改了裁决不变）"
            elif changed and in_set:
                verdict = "OK（承载）"
            else:
                verdict = "中性（改了裁决不变，且不在条件集里）"
            results.append({"field": field, "where": where, "in_condition_set": in_set,
                            "baseline_exit": b_rc, "exit_after": rc,
                            "verdict_changes": changed, "axes": axes,
                            "waived": bool(locals().get("waived", False)),
                            "waiver": WAIVERS.get(field),
                            "verdict": verdict})
    bad_blind = [r for r in results
                 if r["verdict_changes"] and not r["in_condition_set"] and not r["waived"]]
    bad_alarm = [r for r in results
                 if r["in_condition_set"] and not r["verdict_changes"]]
    waived_rows = [r for r in results
                   if r["verdict_changes"] and not r["in_condition_set"] and r["waived"]]
    if args.json:
        print(json.dumps({"condition_set": CONDITION_SET, "results": results,
                          "drift_blindness": [r["field"] for r in bad_blind],
                          "false_alarms": [r["field"] for r in bad_alarm],
                          "waived": {r["field"]: r["waiver"] for r in waived_rows}},
                         ensure_ascii=False, indent=2))
        return 0 if (not bad_blind and not bad_alarm) else 1
    print("[SENS] 逐字段问：**改了它，裁决会变吗？**（基线 exit=0）")
    print(f"[SENS] 条件集（核验器现在认的）：{', '.join(CONDITION_SET)}")
    for r in results:
        flag = "!!" if (r["verdict"].startswith("drift-blindness")
                        or r["verdict"].startswith("false alarm")) else "  "
        print(f"  {flag} {r['field']:20} {'集内' if r['in_condition_set'] else '集外'}"
              f" 改后 exit={r['exit_after']:<3} 变化={'是' if r['verdict_changes'] else '否'}"
              f"  轴={','.join(r['axes']) or '-':28} {r['verdict']}")
    print(f"[SENS] drift-blindness（改了会变、不在集里、**且无具名豁免**）："
          f"{', '.join(r['field'] for r in bad_blind) or '无'}")
    for r in waived_rows:
        print(f"[SENS] 豁免 {r['field']}：{r['waiver']}")
    print(f"[SENS] false alarm（在集里但改了不变）："
          f"{', '.join(r['field'] for r in bad_alarm) or '无'}")
    print("[SENS] ⚠️ 本表测的是**核验器的裁决**，不是「这个字段重不重要」。")
    return 0 if (not bad_blind and not bad_alarm) else 1


if __name__ == "__main__":
    sys.exit(main())
