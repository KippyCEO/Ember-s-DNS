#!/usr/bin/env python3
"""Ember's DNS Updater - a small GUI that, once a day:

  1. downloads every source blocklist listed in ../lists.csv
  2. cleans + de-duplicates them into plain-domain lists (lists/*.txt, lists/all.txt)
  3. commits the result and pushes it to GitHub

Pure standard library (tkinter, urllib, subprocess). Needs Python 3.9+ and Git.
Run:  pythonw embers_dns_updater.py            (GUI)
      python  embers_dns_updater.py --once     (headless single run)
"""
import argparse
import csv
import datetime as dt
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

APP_NAME = "Ember's DNS Updater"
APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
LOG_PATH = APP_DIR / "updater.log"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
MIN_DOMAINS = 10          # a download with fewer domains is treated as broken
MIN_RATIO = 0.5           # a download shrinking below 50% of last time is treated as broken
MAX_FILE_BYTES = 95_000_000  # GitHub rejects files over 100 MB
DEFAULTS = {"run_time": "03:00", "auto_push": True, "run_at_login": True, "last_run_date": "",
            "build_combined": False}

# --------------------------------------------------------------------------- parsing
DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?\.)+[a-z0-9-]{2,63}$")
HOST_IP_RE = re.compile(r"^(0\.0\.0\.0|127\.0\.0\.1|::1?|::)$")
SKIP = {"localhost", "localhost.localdomain", "local", "broadcasthost",
        "ip6-localhost", "ip6-loopback", "ip6-localnet", "ip6-mcastprefix"}


def parse_line(line):
    """Return the list of domains found on one line of a hosts / domain / adblock list."""
    line = line.strip()
    if not line or line[0] in "#!;[":
        return []
    line = line.split("#", 1)[0].strip()
    if line.startswith("||"):                       # ||example.com^
        m = re.match(r"^\|\|([^/^$*|]+)\^?$", line)
        cands = [m.group(1)] if m else []
    else:
        parts = line.split()
        if len(parts) >= 2 and HOST_IP_RE.match(parts[0]):   # 0.0.0.0 a.com b.com
            cands = parts[1:]
        elif len(parts) == 1:                                  # a.com
            cands = parts
        else:
            cands = []
    out = []
    for c in cands:
        c = c.lower().rstrip(".")
        if c not in SKIP and DOMAIN_RE.match(c):
            out.append(c)
    return out


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "list"


def load_sources(repo):
    with open(repo / "lists.csv", newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("url") or "").startswith(("http", "file:"))]
    used = set()
    for r in rows:
        name = slug(r["category"])
        if name in used:
            name = f"{name}-{slug(r.get('source', ''))[:20]}"
        used.add(name)
        r["file"] = name + ".txt"
    return rows


def fetch(url, log, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": "EmbersDNS-Updater/1.0"})
    last = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001 - network errors vary widely
            last = exc
            log(f"    attempt {attempt}/{retries} failed: {exc}")
            time.sleep(2 * attempt)
    raise RuntimeError(f"download failed: {last}")


def read_body(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [ln.rstrip("\n") for ln in f if ln.strip() and not ln.startswith("#")]


def write_list(path, header, body):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(header) + "\n")
        f.write("\n".join(body) + "\n")


# --------------------------------------------------------------------------- git
def find_git():
    exe = shutil.which("git")
    if exe:
        return exe
    for p in (r"C:\Program Files\Git\cmd\git.exe", r"C:\Program Files (x86)\Git\cmd\git.exe"):
        if os.path.exists(p):
            return p
    return None


def git(args, repo, timeout=300):
    exe = find_git()
    if not exe:
        raise RuntimeError("Git is not installed (or not on PATH).")
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    return subprocess.run([exe] + args, cwd=repo, capture_output=True, text=True,
                          timeout=timeout, creationflags=NO_WINDOW, env=env)


def remote_slug(repo):
    try:
        url = git(["remote", "get-url", "origin"], repo).stdout.strip()
        m = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?$", url)
        return f"{m.group(1)}/{m.group(2)}" if m else None
    except Exception:  # noqa: BLE001
        return None


def commit_and_push(repo, message, log):
    def run(args, **kw):
        log("  $ git " + " ".join(args))
        p = git(args, repo, **kw)
        for ln in (p.stdout + p.stderr).strip().splitlines():
            log("    " + ln)
        return p

    run(["add", "-A", "--", "lists", "stats.json", "README.md"])
    if git(["diff", "--cached", "--quiet"], repo).returncode == 0:
        log("Nothing changed - nothing to commit.")
        return "nothing"
    ident = []
    if not git(["config", "user.name"], repo).stdout.strip():
        ident += ["-c", "user.name=Ember's DNS Updater"]
    if not git(["config", "user.email"], repo).stdout.strip():
        ident += ["-c", "user.email=noreply@users.noreply.github.com"]
    p = run(ident + ["commit", "-m", message])
    if p.returncode != 0:
        raise RuntimeError("git commit failed")
    pull = run(["pull", "--rebase", "--autostash"])
    if pull.returncode != 0:
        log("  (pull skipped/failed - trying push anyway)")
    log("Pushing to GitHub (if a sign-in window appears, sign in once)...")
    push = run(["push", "-u", "origin", "HEAD"], timeout=600)
    if push.returncode != 0:
        raise RuntimeError("git push failed - see log above")
    return "pushed"


# --------------------------------------------------------------------------- update run
def run_update(repo, cfg, log, emit, push=True):
    rows = load_sources(repo)
    lists_dir = repo / "lists"
    lists_dir.mkdir(exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    steps = len(rows) + 2
    emit("progress", 0, steps)
    union, stats, changed, failed = set(), [], [], []

    for i, r in enumerate(rows, 1):
        iid, path = r["file"], lists_dir / r["file"]
        old = read_body(path)
        log(f"[{i}/{len(rows)}] {r['category']}  <-  {r['url']}")
        emit("row", iid, status="Downloading...")
        try:
            text = fetch(r["url"], log)
            domains = set()
            for line in text.splitlines():
                domains.update(parse_line(line))
            if len(domains) < MIN_DOMAINS:
                raise RuntimeError(f"only {len(domains)} domains parsed - ignoring this download")
            if old and len(domains) < MIN_RATIO * len(old):
                raise RuntimeError(f"shrank from {len(old):,} to {len(domains):,} - ignoring this download")
            body = sorted(domains)
            if body == old:
                status, delta = "Unchanged", 0
            else:
                header = [f"# Ember's DNS - {r['category']}", f"# Updated: {stamp}",
                          f"# Domains: {len(body)}", f"# Source: {r['url']}",
                          f"# Source license: {r['license']} ({r.get('source', '')})"]
                write_list(path, header, body)
                status, delta = "Updated", len(body) - len(old)
                changed.append(r["file"])
            log(f"    {len(body):,} domains - {status}")
            emit("row", iid, domains=len(body), delta=delta, status=status)
        except Exception as exc:  # noqa: BLE001
            log(f"    FAILED: {exc}")
            failed.append(r["category"])
            body = old
            emit("row", iid, domains=len(old) if old else "", delta="", status="Failed - kept previous")
        if body:
            union.update(body)
            stats.append({"category": r["category"], "file": f"lists/{r['file']}", "domains": len(body),
                          "source": r.get("source", ""), "license": r["license"], "url": r["url"]})
        emit("progress", i, steps)

    # optional combined list (off by default: it is huge and bloats the repo)
    all_body = sorted(union)
    all_path = lists_dir / "all.txt"
    combined = bool(cfg.get("build_combined", False))
    if not combined:
        if all_path.exists():
            all_path.unlink()
            changed.append("all.txt (removed)")
            log("Combined list is disabled - removed lists/all.txt")
    else:
        log("Building combined list (all.txt)...")
        if sum(len(d) + 1 for d in all_body) > MAX_FILE_BYTES:
            log("  combined list would exceed GitHub's file size limit - skipped")
        elif all_body != read_body(all_path):
            write_list(all_path,
                       ["# Ember's DNS - all categories combined", f"# Updated: {stamp}",
                        f"# Domains: {len(all_body)}"], all_body)
            changed.append("all.txt")
    emit("progress", len(rows) + 1, steps)

    # stats.json + README table
    stats_path = repo / "stats.json"
    if changed or not stats_path.exists():
        with open(stats_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"generated": stamp, "total_unique_domains": len(all_body), "lists": stats}, f, indent=2)
            f.write("\n")
    update_readme(repo, stats, len(all_body), log, combined)
    emit("progress", steps, steps)

    summary = f"{len(changed)} file(s) changed, {len(failed)} failed, {len(all_body):,} unique domains"
    log("Build finished: " + summary)
    result = "built"
    if push and cfg.get("auto_push", True):
        msg = f"Daily update {dt.date.today().isoformat()} ({len(changed)} file(s) changed)"
        result = commit_and_push(repo, msg, log)
    elif not push:
        log("Push disabled for this run.")
    return {"changed": changed, "failed": failed, "total": len(all_body), "result": result, "summary": summary}


def update_readme(repo, stats, total, log, combined=False):
    readme = repo / "README.md"
    if not readme.exists():
        return
    start, end = "<!-- BUILT-LISTS:START -->", "<!-- BUILT-LISTS:END -->"
    text = readme.read_text(encoding="utf-8")
    if start not in text or end not in text:
        return
    slug_ = remote_slug(repo) or ""
    base = f"https://raw.githubusercontent.com/{slug_}/main/" if slug_ else ""
    lines = ["| Category | Domains | Subscribe URL |", "|---|---|---|"]
    for s in stats:
        lines.append(f"| {s['category']} | {s['domains']:,} | `{base}{s['file']}` |")
    if combined:
        lines.append(f"| **All categories combined** | {total:,} | `{base}lists/all.txt` |")
    block = start + "\n" + "\n".join(lines) + "\n" + end
    new = re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _m: block, text, flags=re.S)
    if new != text:
        readme.write_text(new, encoding="utf-8", newline="\n")
        log("README list table refreshed.")


# --------------------------------------------------------------------------- config / startup
def load_config():
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001
        pass
    return cfg


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def startup_file():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Microsoft/Windows/Start Menu/Programs/Startup/EmbersDNSUpdater.vbs"


def set_startup(enabled):
    f = startup_file()
    if f is None:
        return
    if enabled:
        exe = Path(sys.executable)
        pyw = exe.with_name("pythonw.exe")
        runner = pyw if pyw.exists() else exe
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(
            'Set s = CreateObject("WScript.Shell")\r\n'
            f's.Run """{runner}"" ""{Path(__file__).resolve()}"" --minimized", 1, False\r\n',
            encoding="utf-8")
    elif f.exists():
        f.unlink()


def make_logger(sink=None):
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > 2_000_000:
            LOG_PATH.unlink()
    except OSError:
        pass

    def log(msg):
        line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass
        (sink or print)(line)
    return log


# --------------------------------------------------------------------------- GUI
def run_gui(repo, minimized):
    import tkinter as tk
    from tkinter import messagebox, scrolledtext, ttk

    cfg = load_config()
    rows = load_sources(repo)
    q = queue.Queue()
    state = {"running": False, "retry_at": 0.0}

    root = tk.Tk()
    root.title(APP_NAME)
    root.geometry("1000x680")
    root.minsize(820, 520)
    style = ttk.Style(root)
    try:
        style.theme_use("vista" if os.name == "nt" else "clam")
    except tk.TclError:
        pass

    top = ttk.Frame(root, padding=(14, 12, 14, 4))
    top.pack(fill="x")
    ttk.Label(top, text="Ember's DNS Updater", font=("Segoe UI", 18, "bold")).pack(side="left")
    status_var = tk.StringVar(value="Idle")
    ttk.Label(top, textvariable=status_var, font=("Segoe UI", 11)).pack(side="right")

    info = ttk.Frame(root, padding=(14, 0, 14, 6))
    info.pack(fill="x")
    last_var, next_var = tk.StringVar(), tk.StringVar()
    ttk.Label(info, textvariable=last_var).pack(side="left")
    ttk.Label(info, textvariable=next_var).pack(side="right")

    bar = ttk.Frame(root, padding=(14, 4))
    bar.pack(fill="x")
    run_btn = ttk.Button(bar, text="Run now")
    run_btn.pack(side="left")
    ttk.Button(bar, text="Open repo folder",
               command=lambda: os.startfile(repo) if os.name == "nt" else None).pack(side="left", padx=6)
    ttk.Label(bar, text="Daily at (HH:MM):").pack(side="left", padx=(18, 4))
    time_var = tk.StringVar(value=cfg["run_time"])
    ttk.Entry(bar, textvariable=time_var, width=7).pack(side="left")
    push_var = tk.BooleanVar(value=cfg["auto_push"])
    login_var = tk.BooleanVar(value=cfg["run_at_login"])

    def on_settings(*_):
        t = time_var.get().strip()
        try:
            dt.datetime.strptime(t, "%H:%M")
            cfg["run_time"] = t
        except ValueError:
            pass
        cfg["auto_push"] = push_var.get()
        cfg["run_at_login"] = login_var.get()
        save_config(cfg)
        set_startup(cfg["run_at_login"])
        refresh_labels()

    time_var.trace_add("write", on_settings)
    ttk.Checkbutton(bar, text="Push to GitHub", variable=push_var, command=on_settings).pack(side="left", padx=12)
    ttk.Checkbutton(bar, text="Start at Windows login", variable=login_var, command=on_settings).pack(side="left")

    pb = ttk.Progressbar(root, mode="determinate")
    pb.pack(fill="x", padx=14, pady=(6, 6))

    cols = ("list", "domains", "change", "status")
    tree = ttk.Treeview(root, columns=cols, show="headings", height=8)
    for c, w, a in (("list", 360, "w"), ("domains", 110, "e"), ("change", 100, "e"), ("status", 280, "w")):
        tree.heading(c, text=c.title())
        tree.column(c, width=w, anchor=a)
    tree.pack(fill="x", padx=14)
    prev = {}
    try:
        prev = {s["file"].split("/")[-1]: s["domains"]
                for s in json.loads((repo / "stats.json").read_text(encoding="utf-8"))["lists"]}
    except Exception:  # noqa: BLE001
        pass
    for r in rows:
        n = prev.get(r["file"])
        tree.insert("", "end", iid=r["file"], values=(r["category"], f"{n:,}" if n else "", "", "Pending"))

    logbox = scrolledtext.ScrolledText(root, height=12, font=("Consolas", 9), state="disabled", wrap="none")
    logbox.pack(fill="both", expand=True, padx=14, pady=(8, 14))

    def gui_log(line):
        q.put(("log", line))

    log = make_logger(gui_log)

    def emit(kind, *a, **kw):
        q.put((kind, a, kw))

    def next_run():
        hh, mm = map(int, cfg["run_time"].split(":"))
        now = dt.datetime.now()
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if cfg.get("last_run_date") == now.date().isoformat():
            target += dt.timedelta(days=1)
        return target

    def refresh_labels():
        last_var.set(f"Last successful run: {cfg.get('last_run_date') or 'never'}")
        try:
            nr = next_run()
            next_var.set("Next run: due now" if nr <= dt.datetime.now() else f"Next run: {nr:%a %b %d, %H:%M}")
        except Exception:  # noqa: BLE001
            next_var.set("Next run: -")

    def worker():
        try:
            res = run_update(repo, cfg, log, emit, push=True)
            q.put(("done", res, None))
        except Exception as exc:  # noqa: BLE001
            log(f"ERROR: {exc}")
            q.put(("done", None, str(exc)))

    def start_run():
        if state["running"]:
            return
        state["running"] = True
        run_btn.state(["disabled"])
        status_var.set("Running...")
        for r in rows:
            tree.set(r["file"], "status", "Queued")
            tree.set(r["file"], "change", "")
        log("=== Update started ===")
        threading.Thread(target=worker, daemon=True).start()

    run_btn.configure(command=start_run)

    def poll():
        try:
            while True:
                item = q.get_nowait()
                kind = item[0]
                if kind == "log":
                    logbox.configure(state="normal")
                    logbox.insert("end", item[1] + "\n")
                    logbox.see("end")
                    logbox.configure(state="disabled")
                elif kind == "progress":
                    pb.configure(maximum=item[1][1], value=item[1][0])
                elif kind == "row":
                    iid, kw = item[1][0], item[2]
                    if "domains" in kw and kw["domains"] != "":
                        tree.set(iid, "domains", f"{kw['domains']:,}")
                    if "delta" in kw:
                        d = kw["delta"]
                        tree.set(iid, "change", "" if d in ("", 0) else f"{d:+,}")
                    if "status" in kw:
                        tree.set(iid, "status", kw["status"])
                elif kind == "done":
                    state["running"] = False
                    run_btn.state(["!disabled"])
                    res, err = item[1], item[2]
                    if err:
                        status_var.set("Failed - will retry in 1 hour")
                        state["retry_at"] = time.time() + 3600
                    else:
                        status_var.set(f"Done - {res['summary']}")
                        if res["failed"]:
                            state["retry_at"] = time.time() + 3600
                        else:
                            cfg["last_run_date"] = dt.date.today().isoformat()
                            save_config(cfg)
                    refresh_labels()
        except queue.Empty:
            pass
        root.after(150, poll)

    def tick():
        if not state["running"] and time.time() >= state["retry_at"]:
            hh, mm = map(int, cfg["run_time"].split(":"))
            now = dt.datetime.now()
            due = now >= now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if due and cfg.get("last_run_date") != now.date().isoformat():
                log("Scheduled daily run is due.")
                start_run()
        refresh_labels()
        root.after(20000, tick)

    set_startup(cfg["run_at_login"])
    refresh_labels()
    root.after(150, poll)
    root.after(3000, tick)
    if minimized:
        root.iconify()
    log(f"{APP_NAME} started. Repo: {repo}")
    root.mainloop()


# --------------------------------------------------------------------------- entry point
def main():
    ap = argparse.ArgumentParser(description=APP_NAME)
    ap.add_argument("--repo", type=Path, default=APP_DIR.parent, help="path to the repo (contains lists.csv)")
    ap.add_argument("--once", action="store_true", help="run one headless update and exit")
    ap.add_argument("--no-push", action="store_true", help="with --once: build but do not commit/push")
    ap.add_argument("--minimized", action="store_true", help="start the GUI minimized")
    args = ap.parse_args()
    repo = args.repo.resolve()
    if not (repo / "lists.csv").exists():
        sys.exit(f"lists.csv not found in {repo}")
    if args.once:
        log = make_logger()
        res = run_update(repo, load_config(), log, lambda *a, **k: None, push=not args.no_push)
        sys.exit(1 if res["failed"] else 0)
    run_gui(repo, args.minimized)


if __name__ == "__main__":
    main()
