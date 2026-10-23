#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上午 8 点赛果补录任务：抓赛果 → 有更新才提交推送 gh-pages，无更新直接跳过。

为什么需要这层包装（而不是直接跑 update_odds_net.py --results-only）：
  1. `push_to_gh_pages()` 硬性要求当前分支是 master，但本仓库日常工作在 gh-pages，
     且本地 master 落后云端 126 个提交 —— 切过去跑会拿旧文件覆盖工作区，属于高危操作。
     所以这里用 `--no-push` 只做抓取落盘，推送由本脚本按 gh-pages 的正确姿势完成。
  2. 赛果链路每次都会重写 index.html 的 ODDS 内联与 odds_data.json（含 updated 时间戳），
     即使没有任何新赛果也会产生 diff。必须靠 update_odds_net.py 输出的 `[变更判定]`
     判断有没有真赛果变化，无变化就不提交，避免每天一条空提交。

退出码：0 = 成功（含"无更新跳过"）；1 = 抓取失败或推送失败；2 = 环境不满足（分支/仓库状态）。
"""
import os
import re
import subprocess
import sys
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
BRANCH = "gh-pages"

# 只提交赛果链路的产物；严禁 add -A（会把 _ 开头的调试脚本、记忆文件一起带进去）
RESULT_FILES = ["index.html", "results_data.json", "results_history", "odds_history"]


def run(cmd, timeout=1800, check=False):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout, env=env)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} 失败 ({r.returncode})")
    return r


def git(*args, timeout=180, check=False):
    return run(["git", "--no-pager"] + list(args), timeout=timeout, check=check)


def out(r):
    return ((r.stdout or "") + (r.stderr or "")).strip()


def say(msg):
    print(msg, flush=True)


def fail(msg, code=1):
    say(f"  ❌ {msg}")
    return code


def main():
    say("=" * 60)
    say(f"  赛果补录（{datetime.datetime.now():%Y-%m-%d %H:%M}）")
    say("=" * 60)

    # --- 环境前置检查：不在 rebase/merge 中间态，且分支正确 ---
    git_dir = os.path.join(BASE, ".git")
    for state in ("rebase-merge", "rebase-apply", "MERGE_HEAD"):
        if os.path.exists(os.path.join(git_dir, state)):
            return fail(f"仓库处于 {state} 中间态，先人工处理再跑定时任务", 2)

    br = out(git("rev-parse", "--abbrev-ref", "HEAD")).strip()
    if br != BRANCH:
        return fail(f"当前分支是 {br}，不是 {BRANCH}；本脚本不做分支切换（避免误伤工作区）", 2)

    # --- 抓赛果（只落盘，不推送）---
    say("\n[1/3] 抓取赛果（--no-push --results-only）...")
    r = run([sys.executable, "update_odds_net.py", "--no-push", "--results-only"])
    text = out(r)
    # 只回显关键行，避免把整份抓取日志刷进任务记录
    for ln in text.splitlines():
        if any(k in ln for k in ("[变更判定]", "新增赛果", "赛果更新完成", "致命错误",
                                 "[错误]", "[警告]", "解析成功", "🎯")):
            say("   " + ln.strip())

    if r.returncode != 0:
        return fail("赛果抓取失败（见上方日志）", 1)

    m = re.search(r"\[变更判定\]\s*新增赛果\s*(\d+)\s*条\s*/\s*更新赛果\s*(\d+)\s*条", text)
    if not m:
        return fail("未能在输出里找到 [变更判定]，无法确认是否有新赛果，为安全起见不推送", 1)
    added, updated = int(m.group(1)), int(m.group(2))
    say(f"\n[2/3] 变更判定：新增 {added} 条 / 更新 {updated} 条")

    if added == 0 and updated == 0:
        # 无赛果变化时，顺手把被顺带刷新的 odds_data.json 时间戳还原，
        # 免得工作区长期挂着一条无意义改动、干扰下一次人工排查。
        if out(git("status", "--porcelain", "odds_data.json")).strip():
            git("checkout", "--", "odds_data.json")
            say("   （已还原 odds_data.json 的 updated 时间戳，非数据变化）")
        say("  ✅ 无赛果更新 → 跳过提交与推送")
        return 0

    # --- 有更新：提交并推送 gh-pages ---
    say("\n[3/3] 提交并推送 gh-pages...")
    existing = [f for f in RESULT_FILES if os.path.exists(os.path.join(BASE, f))]
    git("add", *existing)
    staged = out(git("diff", "--cached", "--name-only"))
    if not staged.strip():
        say("  ℹ️  暂存区为空（数据虽判定有变化但文件内容一致），跳过提交")
        return 0
    say("   待提交：" + ", ".join(staged.split()))

    msg = (f"data: 赛果补录 新增{added}条/更新{updated}条"
           f"（{datetime.date.today().isoformat()} 08:00 定时任务）")
    c = git("commit", "-m", msg)
    if c.returncode != 0:
        return fail(f"commit 失败：{out(c)[:200]}", 1)
    say(f"   ✅ 已提交：{msg}")

    # 先直接 push：绝大多数情况是 fast-forward，不需要 rebase。
    # （2026-10-23 实测：工作区存在未提交的脚本改动时 rebase 会被 git 直接拒绝，
    #   报出来像"冲突"，实际是 unstaged changes —— 所以只在真的被拒后才 rebase。）
    p = git("push", "origin", f"HEAD:{BRANCH}", timeout=180)
    if p.returncode != 0:
        say("   ⚠️  直接推送被拒（远端有新提交），改为 rebase 后重试...")
        f = git("fetch", "origin", BRANCH, timeout=180)
        if f.returncode != 0:
            return fail(f"fetch 失败：{out(f)[:200]}", 1)
        remote_sha = out(git("rev-parse", f"origin/{BRANCH}")).strip()
        if not remote_sha:
            return fail("拿不到 origin/gh-pages 的 SHA，放弃推送", 1)
        # --autostash：工作区可能残留脚本改动，交给 git 自动暂存/恢复，避免 rebase 被拒
        rb = git("rebase", "--autostash", "--no-fork-point", remote_sha, timeout=180)
        if rb.returncode != 0:
            git("rebase", "--abort")
            return fail("rebase 失败，已 abort；请人工处理后重跑（本次未推送）", 1)
        p = git("push", "origin", f"HEAD:{BRANCH}", timeout=180)
        if p.returncode != 0:
            return fail(f"push 失败：{out(p)[:300]}", 1)

    head = out(git("rev-parse", "--short", "HEAD")).strip()
    say(f"  ✅ 已推送 gh-pages（{head}）")
    say("\n赛果补录完成。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"  ❌ 任务异常：{type(e).__name__}: {e}", flush=True)
        sys.exit(1)
