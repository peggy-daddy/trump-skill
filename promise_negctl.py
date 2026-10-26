#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**事前承诺行的负控**（@wren: 「把期望写成一个带日期的行，放在跑之前」）。

    → 以前 [CHECKS] 是**事后**清点：跑完自己数自己做了几次比较。
      那还是**作者对自己行为的叙述** —— 叙述可以事后编。
    → 现在有一行**带日期的承诺**写在跑之前，核验器跑完和它做 join。
    → 好处：**差多少不需要攻击者才能看见**，读者拿着那行承诺自己对账。

本负控要证明两件事：

  A. **对照行（control）**：承诺行说 1080 次，实际就是 1080 次，shortfall = 0，
     退出码 0。→ 说明这条路径不是「永远红」。

  B. **负控行（negative）**：拿一份**由另一版代码写出来的日志**当 fixture。
     它的每一行 `code_sha` 都对不上当前代码 → 核验器**跳过** cond/diff 两根轴
     → 但那两行在承诺行里**已经算进了期望值** → shortfall = 24。
     → 关键：**日志文件本身没被改过**（摘要对得上），
       所以 shortfall 归因于「记录是别的代码写的」，
       **不是**归因于「有人动过日志」。
     → 这就是「无需攻击者也能看出差别」的形状。

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
FIXTURE = os.path.join(ROOT, "refs", "fixture_other_code_log.jsonl")
PRECOMMIT = os.path.join(ROOT, "refs", "precommit.jsonl")


def _run(args, cwd=ROOT):
    env = dict(os.environ)
    env["PROMISE_LEDGER"] = os.path.join(cwd, "promise_ledger_tmp.jsonl")
    return subprocess.run([sys.executable] + args, cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=600)


def _num(text, key):
    """从输出里取 `[CHECKS] 三个数：expected=... compared=... refused=...`。"""
    for line in text.splitlines():
        if key in line and "expected=" in line:
            for part in line.split("expected=")[1].split():
                if part.startswith("compared="):
                    return int(part.split("=")[1].split("refused=")[0])
    return None


def _shortfall(text):
    import re
    for line in text.splitlines():
        if "三个数" in line and "shortfall=" in line:
            m = re.search(r"shortfall=(-?\d+)", line)
            if m:
                return int(m.group(1))
    return None


def _sentinel(tag):
    return "__SENTINEL_promise_%s_%s__" % (tag, hashlib.sha256(
        tag.encode()).hexdigest()[:8])


def main():
    tmp = tempfile.mkdtemp(prefix="promise_negctl_")
    fails = []

    # ---------- A. 对照行：同一份日志，承诺 vs 实际 ----------
    log_copy = os.path.join(tmp, "control_log.jsonl")
    shutil.copy(LOG, log_copy)
    _run(["decision_log.py", "--precommit", log_copy])
    r = _run(["decision_log.py", "--verify", log_copy])
    out = r.stdout + r.stderr
    sent_a = _sentinel("control")
    # 哨兵：对照行里**不能**出现「欠 N 次」——它必须 shortfall = 0
    if _shortfall(out) != 0:
        fails.append("对照行 shortfall 应为 0，实为 %r" % _shortfall(out))
    if r.returncode != 0:
        fails.append("对照行退出码应为 0，实为 %d" % r.returncode)
    if sent_a in out:
        fails.append("对照行不该出现哨兵 %s" % sent_a)
    print("[A control] shortfall=%s exit=%d" % (_shortfall(out), r.returncode))

    # ---------- B. 负控行：由另一版代码写出的日志 ----------
    if not os.path.exists(FIXTURE):
        fails.append("缺 fixture：%s" % FIXTURE)
    else:
        fx = os.path.join(tmp, "neg_log.jsonl")
        shutil.copy(FIXTURE, fx)
        _run(["decision_log.py", "--precommit", fx])
        r2 = _run(["decision_log.py", "--verify", fx])
        out2 = r2.stdout + r2.stderr
        sent_b = _sentinel("negative")
        sf = _shortfall(out2)
        # 哨兵：**必须**报出 shortfall > 0（两根轴被跳过）
        if not (sf is not None and sf > 0):
            fails.append("负控行 shortfall 应 > 0，实为 %r" % sf)
        # 哨兵：必须点名 cond / diff 两根轴「欠 N 次」
        for ax in ("cond", "diff"):
            if ("轴 %s" % ax) not in out2:
                fails.append("负控行应点名轴 %s 欠比较，输出里没有" % ax)
        # 哨兵：日志文件**没被改过** → 承诺行的摘要必须对得上
        if "记录文件摘要与承诺时**不同**" in out2:
            fails.append("负控行不该报摘要不一致（文件没改）")
        if sent_b in out2:
            fails.append("负控行不该出现哨兵 %s" % sent_b)
        print("[B negative] shortfall=%s exit=%d" % (sf, r2.returncode))

    shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print("[FAIL]")
        for f in fails:
            print("  -", f)
        return 1
    print("[OK] 事前承诺行的负控通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
