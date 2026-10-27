#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**理由字段的负控**（@wren: 「一轮如果在理由里引用了 rule / cutoff / tie_break，
却从没读过那些字段，这一轮就该**判失败**，而不是记一笔。」）

v0.31.0 把「只写不读」的理由字段（rule / cutoff / tie_break /
production_reason / considered_causes）接进了核验路径，
并且加了两个**互相独立**的观察者（计数器 + 追踪器）来盯住**报数器自己**。
本负控要证明四件事：

  A. **对照行**：原样的日志 → exit 0，VERDICT=verified，
     没有任何 [REASON] / [CAUSE] 行 → 说明这条路径不是「永远红」。

  B. **理由被改**：把一条兜底记录的 `cutoff` 改成假值，
     **并且把该行的 hash 重算成新的** → 摘要轴看不见它
     → 只有**理由轴**能抓住 → 必须 exit 非零（bit1），
     而且报告里必须**原样打印被改的那个值**（哨兵断言：
     「控制通过了，却没证明走过那条路径」是假阳性）。

  C. **命中情况被改**：改 `considered_causes` 里的命中数，同样重算 hash
     → 只能被 **cause 轴**抓住。

  D. **报数器自己撒谎**：把核验器副本里的 `_axis_done["cond"] += 1`
     删掉（**模拟 v0.29.0 那个真实缺陷**：轴跑了却从没报数）
     → 追踪器会看到 cond 轴**真的跑了**（它读了 profile_hash），
       但计数器没动 → 必须报出「**跑了没报数 180 次**」
     → exit 带 bit7（128），VERDICT=unsound。
     → 这一行证明的是：**这次新增的第三个桶不是装饰**。

每行都带**唯一哨兵**，并且断言核验器**真的读到了被改的那个字段**。
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "decision-log.jsonl")


def _run(args, cwd=ROOT, env_extra=None):
    env = dict(os.environ)
    env["PROMISE_LEDGER"] = os.path.join(cwd, "promise_ledger_tmp.jsonl")
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable] + args, cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=900)


def _sentinel(tag):
    return "__SENTINEL_reason_%s_%s__" % (tag, hashlib.sha256(
        tag.encode()).hexdigest()[:8])


def _rehash(rec):
    """**按核验器自己的配方**重算这一行的自述摘要。"""
    body = json.dumps({k: v for k, v in rec.items() if k != "hash"},
                      ensure_ascii=False, sort_keys=True)
    rec["hash"] = hashlib.sha256(body.encode()).hexdigest()[:12]
    return rec


def _load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def _write(rows, path):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _has(out, needle):
    return needle in out


def main():
    tmp = tempfile.mkdtemp(prefix="reason_negctl_")
    fails = []

    # ---------- A. 对照行：原样的日志 ----------
    ctl_log = os.path.join(tmp, "control_log.jsonl")
    shutil.copy(LOG, ctl_log)
    _run(["decision_log.py", "--precommit", ctl_log])
    r = _run(["decision_log.py", "--verify", ctl_log])
    out = r.stdout + r.stderr
    if r.returncode != 0:
        fails.append("A 对照行退出码 %d（应为 0）" % r.returncode)
    if "VERDICT=verified" not in out:
        fails.append("A 对照行没有 VERDICT=verified")
    if "[REASON]" in out or "[CAUSE]" in out:
        fails.append("A 对照行不该出现 [REASON]/[CAUSE] 失败行")
    print("[A] 对照行：exit=%d verdict=%s" % (
        r.returncode,
        "verified" if "VERDICT=verified" in out else "?"))

    # ---------- B. 理由被改（并且把摘要一起重算，摘要轴看不见）----------
    rows = _load(LOG)
    tgt = None
    for x in rows:
        if x.get("source") == "fallback" and x.get("cutoff"):
            tgt = x
            break
    if tgt is None:
        fails.append("B 找不到兜底记录")
    else:
        sent = _sentinel("cutoff")
        tampered = dict(tgt)
        tampered["cutoff"] = "第 3 名分数 = " + sent
        _rehash(tampered)
        rows2 = [tampered if r is tgt else r for r in rows]
        b_log = os.path.join(tmp, "tampered_reason_log.jsonl")
        _write(rows2, b_log)
        _run(["decision_log.py", "--precommit", b_log])
        r = _run(["decision_log.py", "--verify", b_log])
        out = r.stdout + r.stderr
        if r.returncode == 0:
            fails.append("B 理由被改却 exit 0 → 理由轴没抓住")
        if not (r.returncode & 2):
            fails.append("B 退出码 %d 不含 bit1（条件/理由被改）" % r.returncode)
        if not _has(out, "[REASON]"):
            fails.append("B 没有 [REASON] 行")
        if not _has(out, "field=cutoff"):
            fails.append("B 报告没有点名 field=cutoff")
        if not _has(out, sent):
            fails.append("B 报告没有原样打印被改的值（哨兵 %s）" % sent)
        print("[B] 理由被改：exit=%d  [REASON]=%s  哨兵打印=%s" % (
            r.returncode, _has(out, "[REASON]"), _has(out, sent)))

    # ---------- C. 命中情况被改（considered_causes）----------
    rows = _load(LOG)
    tgt = None
    for x in rows:
        cc = x.get("considered_causes")
        if isinstance(cc, list) and cc:
            tgt = x
            break
    if tgt is None:
        fails.append("C 找不到带 considered_causes 的记录")
    else:
        sent = _sentinel("causes")
        tampered = json.loads(json.dumps(tgt))
        cc = tampered["considered_causes"]
        cc[0]["keyword_hits"] = cc[0].get("keyword_hits", 0) + 7
        tampered["production_reason"] = (tampered.get("production_reason") or "") + sent
        _rehash(tampered)
        rows2 = [tampered if r is tgt else r for r in rows]
        c_log = os.path.join(tmp, "tampered_cause_log.jsonl")
        _write(rows2, c_log)
        _run(["decision_log.py", "--precommit", c_log])
        r = _run(["decision_log.py", "--verify", c_log])
        out = r.stdout + r.stderr
        if r.returncode == 0:
            fails.append("C 命中情况被改却 exit 0 → cause 轴没抓住")
        if not (r.returncode & 2):
            fails.append("C 退出码 %d 不含 bit1" % r.returncode)
        if not _has(out, "[CAUSE]"):
            fails.append("C 没有 [CAUSE] 行")
        if not _has(out, "considered_causes"):
            fails.append("C 报告没有点名 considered_causes")
        print("[C] 命中情况被改：exit=%d  [CAUSE]=%s" % (
            r.returncode, _has(out, "[CAUSE]")))

    # ---------- D. 报数器自己撒谎（模拟 v0.29.0 的真实缺陷）----------
    # → 用 **git clone** 而不是 cp：副本里 HEAD 相同、代码可改。
    # → 关键一步：**在副本里用这份（坏掉的）代码重新生成日志**。
    #   因为 v0.31.0 起 code_sha 钉的是**源码内容**而不是提交号 →
    #   副本里改了源码 → 摘要就变 → 旧日志会漂移 → cond 轴被赊销 →
    #   那样就**测不到**坏掉的计数器了。
    #   → 所以：**先改源码 → 再生成日志 → 再核验**，
    #   这正是 v0.29.0 那个缺陷的**真实形状**：
    #   「轴跑了，但同一份代码里的计数器不报数」。
    clone = os.path.join(tmp, "clone")
    r = subprocess.run(["git", "clone", "-q", ROOT, clone],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        fails.append("D git clone 失败：" + (r.stderr or "")[:200])
    else:
        src = os.path.join(clone, "decision_log.py")
        txt = open(src, encoding="utf-8").read()
        needle = '_axis_done["cond"] += 1'
        if needle not in txt:
            fails.append("D 副本里找不到 " + needle)
        else:
            txt = txt.replace(needle, 'pass  # 故意不报数（模拟 v0.29.0 缺陷）')
            open(src, "w", encoding="utf-8").write(txt)
            g = _run(["decision_log.py", "--permutations", "14"], cwd=clone)
            if g.returncode != 0:
                fails.append("D 副本里生成日志失败：" + (g.stderr or "")[:300])
            r = _run(["decision_log.py", "--verify",
                      os.path.join(clone, "decision-log.jsonl")], cwd=clone)
            out = r.stdout + r.stderr
            if not _has(out, "跑了没报数"):
                fails.append("D 没有报出「跑了没报数」→ 第三个桶是装饰")
            if not (r.returncode & 128):
                fails.append("D 退出码 %d 不含 bit7（报告不成立）" % r.returncode)
            if "VERDICT=unsound" not in out:
                fails.append("D 没有 VERDICT=unsound")
            print("[D] 报数器坏掉：exit=%d  报了没报数=%s  verdict=unsound=%s" % (
                r.returncode, _has(out, "跑了没报数"),
                "VERDICT=unsound" in out))

    if fails:
        print("\n[F] 负控失败 %d 项：" % len(fails))
        for f in fails:
            print("   -", f)
        return 1
    print("\n[F] 负控全过：理由轴 / cause 轴 / 报数器自检 三条都真的会红")
    return 0


if __name__ == "__main__":
    sys.exit(main())
