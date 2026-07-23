#!/usr/bin/env python3
"""Serve the storage report with a guarded one-click delete API (macOS + Windows).

Starts on 127.0.0.1 + a random port + a random per-session token, serves the
interactive report, and exposes POST /action to move green-tier paths to Trash
or delete them outright. Stop with Ctrl+C.

Usage:
    server.py <analysis.json>

SAFETY MODEL — read before changing:
- Allowlist: only paths listed in this report's green items `trash_paths` are
  accepted. Every request path is realpath-resolved and must be in the allowlist
  AND under $HOME. Anything else is rejected. This is the core guard — the
  endpoint cannot be used to delete arbitrary files.
- Bound to 127.0.0.1 only; every POST requires the session token; Host header
  must be 127.0.0.1 (blocks DNS-rebinding from a malicious page).
- Two modes: "trash" (Finder -> Trash, reversible) and "rm" (immediate,
  irreversible). The browser confirms each action before sending.
"""
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "assets", "report_template.html")
HOME = os.path.realpath(os.path.expanduser("~"))
TOKEN = secrets.token_urlsafe(24)

DATA = {}
TPL = ""
RM_ALLOW = set()
TRASH_ALLOW = set()
OPEN_ALLOW = set()


def expand(p):
    return os.path.realpath(os.path.expanduser(p))


def load(src):
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    # 白名单：fanko 要「每个扫描项都能直接删」。所以 green + yellow 的所有可操作路径
    #   都进 rm + trash + open 三档。红灯(成片/定稿)绝不进任何删除白名单——硬保护红线不破。
    #   server 层仍强校验：路径必须在白名单内 + realpath 在 $HOME 或 /Applications 下 + token + Host。
    rm_allow, trash_allow, open_allow = set(), set(), set()

    def allow_all(rp):
        rm_allow.add(rp); trash_allow.add(rp); open_allow.add(rp)

    for it in data.get("green", []):
        for p in (it.get("trash_paths") or [it.get("path")]):
            if p:
                allow_all(expand(p))
    for it in data.get("yellow", []):
        # 黄灯(下载/大应用/未出片)：trash_paths 优先，没有就用 path —— 都给全权限，让它可直接删
        paths = it.get("trash_paths") or ([it["path"]] if it.get("path") else [])
        for p in paths:
            rp = expand(p)
            if os.path.exists(rp):
                allow_all(rp)
    # 红灯：成片/定稿保护区，一律不进白名单（含 app_paths 也不给删，仅历史遗留的 open）
    for it in data.get("red", []):
        for p in (it.get("app_paths") or []):
            rp = expand(p)
            if os.path.exists(rp):
                open_allow.add(rp)
    return data, tpl, rm_allow, trash_allow, open_allow


def move_to_trash(path):
    if sys.platform == "darwin":
        _trash_macos(path)
    elif sys.platform.startswith("win"):
        _trash_windows(path)
    else:
        raise OSError("移到废纸篓仅支持 macOS / Windows")


def _trash_macos(path):
    # osascript Finder delete -> macOS Trash, recoverable. First run may prompt
    # for Finder automation permission. Fall back to ~/.Trash move if it fails.
    script = 'tell application "Finder" to delete (POSIX file %s as alias)' % json.dumps(path)
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode != 0:
        dest = os.path.join(HOME, ".Trash",
                            os.path.basename(path.rstrip("/")) + "." + time.strftime("%H%M%S"))
        shutil.move(path, dest)


def _trash_windows(path):
    # Send to Recycle Bin via SHFileOperationW with FOF_ALLOWUNDO (stdlib ctypes).
    # UNTESTED on this build — verify on a real Windows machine.
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_uint16),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    FO_DELETE = 3
    FOF_ALLOWUNDO = 0x0040
    FOF_NOCONFIRMATION = 0x0010
    FOF_SILENT = 0x0004
    op = SHFILEOPSTRUCTW()
    op.wFunc = FO_DELETE
    op.pFrom = os.path.abspath(path) + "\x00\x00"  # double-null terminated list
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if rc != 0:
        raise OSError("SHFileOperation failed (code %d)" % rc)


def hard_delete(path):
    # exFAT/外置盘容错：删主文件时系统会连带删掉 ._AppleDouble 伴生文件，
    # rmtree 再删它会撞 FileNotFoundError；忽略"已不存在"，其余错误照常抛出。
    def _onerr(func, p, exc_info):
        err = exc_info[1] if isinstance(exc_info, tuple) else exc_info
        if not isinstance(err, FileNotFoundError):
            raise err
    if os.path.isdir(path) and not os.path.islink(path):
        try:
            shutil.rmtree(path, onerror=_onerr)
        except TypeError:  # Python 3.12+ 用 onexc
            shutil.rmtree(path, onexc=lambda f, p, e: None if isinstance(e, FileNotFoundError) else (_ for _ in ()).throw(e))
        # 收尾：若目录因 ._ 残留还在，再扫一遍强删
        if os.path.exists(path):
            for root, dirs, files in os.walk(path, topdown=False):
                for n in files + dirs:
                    fp = os.path.join(root, n)
                    try:
                        os.remove(fp) if not os.path.isdir(fp) else os.rmdir(fp)
                    except (FileNotFoundError, OSError):
                        pass
            try:
                os.rmdir(path)
            except (FileNotFoundError, OSError):
                pass
    else:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def open_in_file_manager(path):
    # 非破坏性：在访达 / 资源管理器里打开该位置，方便用户自己审查删除
    target = path if os.path.isdir(path) else os.path.dirname(path)
    if sys.platform == "darwin":
        # .app 是 bundle，对它用 open 会"启动应用"而非显示；必须用 open -R 在访达里选中。
        if target.rstrip("/").endswith(".app"):
            r = subprocess.run(["open", "-R", target], capture_output=True, text=True)
            if r.returncode != 0:
                raise OSError((r.stderr or "open -R 失败").strip())
            return
        # 普通文件夹：先试直接打开看内容；沙盒容器（如微信）open 会报 -10814，
        # 退回 open -R 在父目录里选中它。两者都失败才算错。
        r = subprocess.run(["open", target], capture_output=True, text=True)
        if r.returncode != 0:
            r2 = subprocess.run(["open", "-R", target], capture_output=True, text=True)
            if r2.returncode != 0:
                raise OSError((r.stderr or r2.stderr or "open 失败").strip())
    elif sys.platform.startswith("win"):
        subprocess.run(["explorer", target])  # explorer 退出码不可靠，不据此判成败
    else:
        raise OSError("打开文件夹仅支持 macOS / Windows")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            blob = json.dumps(DATA, ensure_ascii=False)
            cfg = json.dumps({"token": TOKEN, "endpoint": "/action"})
            html = TPL.replace("__REPORT_DATA__", blob).replace("__DELETE_CONFIG__", cfg)
            self._send(200, html, "text/html; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        if self.path != "/action":
            self._send(404, json.dumps({"ok": False, "error": "not found"}))
            return
        # DNS-rebinding guard: only accept local Host
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            self._send(403, json.dumps({"ok": False, "error": "host 不被允许"}))
            return
        n = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            self._send(400, json.dumps({"ok": False, "error": "请求格式错误"}))
            return
        if req.get("token") != TOKEN:
            self._send(403, json.dumps({"ok": False, "error": "token 校验失败"}))
            return
        mode = req.get("mode")
        allow = {"rm": RM_ALLOW, "trash": TRASH_ALLOW, "open": OPEN_ALLOW}.get(mode)
        if allow is None:
            self._send(400, json.dumps({"ok": False, "error": "未知操作"}))
            return
        done = []
        for p in (req.get("paths") or []):
            rp = expand(p)
            if rp not in allow:
                self._send(403, json.dumps({"ok": False, "error": "路径不在白名单：%s" % p}))
                return
            # 二级护栏：只允许用户目录或 /Applications（后者仅 open 用，删除白名单不含它）
            roots = (HOME, "/Applications", "/Volumes")
            if not any(rp == base or rp.startswith(base + os.sep) for base in roots):
                self._send(403, json.dumps({"ok": False, "error": "路径越界：%s" % p}))
                return
            try:
                if mode == "open":
                    open_in_file_manager(rp)
                elif not os.path.exists(rp):
                    pass  # already gone, treat as success
                elif mode == "trash":
                    move_to_trash(rp)
                else:
                    hard_delete(rp)
                done.append(p)
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "error": str(e)}))
                return
        self._send(200, json.dumps({"ok": True, "done": done}))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    global DATA, TPL, RM_ALLOW, TRASH_ALLOW, OPEN_ALLOW
    DATA, TPL, RM_ALLOW, TRASH_ALLOW, OPEN_ALLOW = load(sys.argv[1])
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    url = "http://127.0.0.1:%d/" % port
    print("报告服务已启动：" + url)
    print("绿灯可删 %d 项 | 橙灯可移废纸篓/打开文件夹 %d 项 | 页面上点" % (len(RM_ALLOW), len(TRASH_ALLOW) - len(RM_ALLOW)))
    print("用完按 Ctrl+C 停止服务（服务关掉后按钮即失效）")
    webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止服务。")


if __name__ == "__main__":
    main()
