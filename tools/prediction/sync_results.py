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
# version.txt 是缓存刷新号，赛果落盘会自增，必须跟数据一起走，否则线上不刷新
RESULT_FILES = ["index.html", "results_data.json", "results_history", "odds_history", "version.txt"]

# 本脚本自己的提交信息前缀，用于识别「上次未推送的补录提交」
OWN_COMMIT_PREFIX = "data: 赛果补录"


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


def _existing_tracked():
    return [p for p in RESULT_FILES if os.path.exists(os.path.join(BASE, p))]


def align_to_remote():
    """把本地对齐到远端 gh-pages 基线，返回 True 表示可以继续抓赛果。

    为什么必须先对齐（这是连续三天推送失败的根因）：
      本地克隆长期落后远端若干次「自动更新赔率+赛果」提交。若直接在旧基线上重算赛果
      再推送，必然 non-fast-forward；此时 rebase 要把本次补录的 diff 重放到远端，
      而两侧同时改 index.html / results_data.json / results_history/ —— 数据类 JSON
      无法自动合并，rebase 恒失败（10-24、10-25、10-26 同一现象）。

    正确姿势是「先站到远端基线上再算」：赛果来自口径稳定的上游 API，同一天重算结果
    一致，所以丢掉上次未推送的补录提交、回到远端基线重算，不会丢任何赛果。
    """
    f = git("fetch", "origin", BRANCH, timeout=300)
    if f.returncode != 0:
        say(f"   ⚠️  fetch 失败，跳过基线对齐（本次推送可能被拒）：{out(f)[:150]}")
        return True
    remote_sha = out(git("rev-parse", f"origin/{BRANCH}")).strip()
    head = out(git("rev-parse", "HEAD")).strip()
    if not remote_sha:
        say("   ⚠️  取不到 origin/gh-pages 的 SHA，跳过基线对齐")
        return True
    if head == remote_sha:
        say(f"   ✅ 基线已是最新（{remote_sha[:8]}）")
        return True

    # 情形一：本地是远端祖先（纯落后）→ 直接快进，不产生任何数据风险
    if git("merge-base", "--is-ancestor", "HEAD", remote_sha).returncode == 0:
        n = out(git("rev-list", "--count", f"HEAD..{remote_sha}")).strip()
        m = git("merge", "--ff-only", remote_sha)
        if m.returncode == 0:
            say(f"   ✅ 已快进到远端 {remote_sha[:8]}（补上落后 {n} 个提交）")
            return True
        k = git("reset", "--keep", remote_sha)
        if k.returncode == 0:
            say(f"   ✅ 已对齐到远端 {remote_sha[:8]}（快进被脏文件挡住，改用 reset --keep）")
            return True
        say(f"   ⚠️  无法快进到远端基线：{out(m)[:150]}")
        return True

    # 情形二：本地与远端分叉 —— 先看分叉的提交都是谁
    rows = []
    for ln in out(git("log", "--format=%H%x09%s", f"{remote_sha}..HEAD")).splitlines():
        if "\t" in ln:
            sha, subj = ln.split("\t", 1)
            rows.append((sha.strip(), subj.strip()))
    data_shes = set(out(git("log", "--format=%H", f"{remote_sha}..HEAD", "--",
                            *RESULT_FILES)).split())

    if rows and all(s.startswith(OWN_COMMIT_PREFIX) for _, s in rows):
        # 全是本脚本上次没推成功的补录提交 → 丢弃重算（幂等）
        r = git("reset", "--keep", remote_sha)
        if r.returncode != 0:
            # 工作区有改动挡路（如 odds_ticks.json），只还原赛果产物，保住其他脏文件
            git("reset", "--soft", remote_sha)
            rr = git("restore", f"--source={remote_sha}", "--staged", "--worktree",
                     "--", *_existing_tracked())
            if rr.returncode != 0:
                return fail(f"无法回到远端基线，需人工处理：{out(rr)[:200]}", 2)
        say(f"   ✅ 已丢弃 {len(rows)} 个未推送的补录提交，回到远端 {remote_sha[:8]} 重新计算")
        return True

    if any(sha in data_shes for sha, _ in rows):
        subs = "; ".join(s for sha, s in rows if sha in data_shes)
        return fail(f"本地有未推送的人工数据提交（{subs[:120]}），不自动丢弃，请人工处理", 2)

    # 分叉的是脚本/记忆类提交，不碰赛果文件 → 常规 rebase 不会冲突
    rb = git("rebase", "--autostash", "--no-fork-point", remote_sha, timeout=180)
    if rb.returncode != 0:
        git("rebase", "--abort")
        return fail(f"rebase 到远端基线失败，已 abort：{out(rb)[:200]}", 2)
    say(f"   ✅ 已 rebase 到远端 {remote_sha[:8]}")
    return True


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

    # --- [0/3] 对齐远端基线：必须放在抓赛果之前 ---
    # 否则就是在旧基线上算数据 → 推送必被拒 → rebase 撞数据类 JSON 冲突。
    say("\n[0/3] 对齐远端 gh-pages 基线...")
    if not align_to_remote():
        return 2

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
    # 显式带 pathspec：即使索引里残留其他文件的旧条目，也不会被这次提交带进去
    c = git("commit", "-m", msg, "--", *existing)
    if c.returncode != 0:
        return fail(f"commit 失败：{out(c)[:200]}", 1)
    # 清掉索引里与本次无关的残留暂存项（如自动更新链路留下的 odds_data.json），
    # 只重置索引、不动工作区文件
    git("reset", "-q")
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
