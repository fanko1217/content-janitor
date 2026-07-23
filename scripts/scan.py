#!/usr/bin/env python3
"""内容清道夫 · 只读扫描器（macOS）。

扫描 fanko 各频道项目，机械第一遍把每个目录/文件分成
  🟢 中间产物(可删)  🟡 整期(可归档)  🔴 成片/定稿(必留·硬保护)
输出一份 report-ready 的 analysis JSON 到 stdout，供 build_report.py / server.py 渲染。
进度打到 stderr。

严格只读：只跑 du / stat / listdir / glob，绝不创建、移动、删除任何东西。
成片/定稿的绝对路径永远不会进入任何 trash_paths（server 层白名单据此拒绝误删）。

用法：
    python3 scan.py [channels.json路径] > /tmp/janitor_analysis.json
不传路径则用脚本同级上一层的 channels.json。
"""
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CFG = os.path.join(HERE, "..", "channels.json")


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def expand(p):
    return os.path.abspath(os.path.expanduser(p))


def human(kb):
    n = float(kb)
    for unit, div in (("GB", 1024 * 1024), ("MB", 1024)):
        if n >= div:
            return "约 %.1f %s" % (n / div, unit)
    return "约 %d KB" % int(n)


def gb(kb):
    return kb / 1024.0 / 1024.0


def du_kb(path, timeout=180):
    """目录/文件占用 KB（du -sk）。读不到返回 0。"""
    try:
        out = subprocess.run(["du", "-sk", path], capture_output=True,
                             text=True, timeout=timeout).stdout
        m = re.match(r"\s*(\d+)", out)
        return int(m.group(1)) if m else 0
    except Exception:
        return 0


def match_any(name, patterns):
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def glob_hit(project, patterns):
    """项目内是否存在匹配任一 glob 的文件（非递归，按 pattern 的层级）。"""
    import glob as _g
    for pat in patterns:
        if _g.glob(os.path.join(project, pat)):
            return True
    return False


def find_matches(project, patterns):
    import glob as _g
    hits = []
    for pat in patterns:
        hits += _g.glob(os.path.join(project, pat))
    return hits


def list_projects(ch):
    """按 layout 列出频道下的项目目录绝对路径。"""
    root = expand(ch["root"])
    if not os.path.isdir(root):
        return []
    layout = ch.get("layout", "projects")
    exclude = ch.get("exclude_name_regex")
    skip = set(ch.get("flat_skip", []))
    projects = []
    if layout == "projects":
        base = os.path.join(root, "projects")
        if not os.path.isdir(base):
            base = root
    else:
        base = root
    try:
        for name in sorted(os.listdir(base)):
            if name.startswith(".") or name in skip:
                continue
            path = os.path.join(base, name)
            if not os.path.isdir(path) or os.path.islink(path):
                continue
            if exclude and re.match(exclude, name):
                continue
            projects.append(path)
    except PermissionError:
        pass
    return projects


def dup_key(name, rules):
    """去时间戳/版本后缀，得到判重基准键。"""
    k = re.sub(rules["dup_suffix_regex"], "", name)
    k = re.sub(rules["timestamp_regex"], "", k)
    return k.strip("_ ")


def subtree_has_finished(path, rules):
    """本层或下一层是否存在成片/定稿（protected_file_globs 命中即视为已出片）。"""
    import glob as _g
    for pat in rules["protected_file_globs"]:
        if _g.glob(os.path.join(path, pat)) or _g.glob(os.path.join(path, "*", pat)):
            return True
    return False


def _uncat_item(label, path, kb, is_dir):
    return {"name": label, "path": path, "size": human(kb), "bucket": "uncat",
            "content_profile": "未归类%s" % ("目录" if is_dir else "文件"),
            "why_manual": "规则不认识它，但它占着 %s。打开看一眼是什么再决定。" % human(kb),
            "disposal": "在访达打开确认内容 → 没用就移废纸篓。",
            "risk": "删前务必确认不是唯一副本的成片/素材。"}


def drill(plabel, path, rules, depth):
    """递归钻进未归类工程夹，把成片(保护)与中间产物(可回收)拆开。
    返回 (out{green,yellow,red,protected_paths}, classified_any)。"""
    out = {"green": [], "yellow": [], "red": [], "protected_paths": []}
    fin = subtree_has_finished(path, rules)
    try:
        children = sorted(os.listdir(path))
    except (PermissionError, OSError):
        return out, False
    min_kb = rules["min_report_mb"] * 1024
    uncat_min = rules.get("uncat_min_mb", 300) * 1024
    classified_any = False
    for name in children:
        cpath = os.path.join(path, name)
        if name.startswith(".") or os.path.islink(cpath):
            continue
        is_dir = os.path.isdir(cpath)
        label = "%s / %s" % (plabel, name)
        if is_dir and name in rules["protected_dirs"]:
            classified_any = True
            continue
        if (not is_dir) and match_any(name, rules["protected_file_globs"]):
            out["protected_paths"].append(os.path.realpath(cpath))
            classified_any = True
            continue
        if match_any(name, rules["junk_names"]):
            kb = du_kb(cpath)
            if kb >= 1024:
                out["green"].append(_green_item(plabel, name, cpath, kb,
                                    "已标记废弃，死重量，可直接回收。", bucket="junk"))
            classified_any = True
            continue
        if is_dir and (name in rules["intermediate_dirs"]
                       or match_any(name, rules["intermediate_dirs"])):
            kb = du_kb(cpath)
            if kb < min_kb:
                classified_any = True
                continue
            if fin:
                out["green"].append(_green_item(plabel, name, cpath, kb,
                                    "中间产物；同夹已有成片，删后可重跑再生。", bucket="bulk"))
            else:
                out["yellow"].append({"name": label, "path": cpath,
                    "size": human(kb), "bucket": "bulk",
                    "content_profile": "中间产物（%s）" % name,
                    "why_manual": "此夹内未检测到成片，删了可能白跑，需确认。",
                    "disposal": "确认已出片或已弃 → 移废纸篓。",
                    "risk": "未出片就删=素材白做。"})
            classified_any = True
            continue
        if (not is_dir) and match_any(name, rules["intermediate_file_globs"]):
            kb = du_kb(cpath)
            if kb >= min_kb:
                out["green"].append(_green_item(plabel, name, cpath, kb,
                                    "过程/预览/副本文件，可回收。", bucket="junk"))
            classified_any = True
            continue
        # 仍未归类 → 大块继续往下钻，钻不动才落 uncat
        kb = du_kb(cpath)
        if kb >= uncat_min:
            if is_dir and depth > 0:
                sub, hit = drill(label, cpath, rules, depth - 1)
                if hit:
                    for k in ("green", "yellow", "red"):
                        out[k] += sub[k]
                    out["protected_paths"] += sub["protected_paths"]
                    classified_any = True
                else:
                    out["yellow"].append(_uncat_item(label, cpath, kb, is_dir))
            else:
                out["yellow"].append(_uncat_item(label, cpath, kb, is_dir))
    return out, classified_any


def classify_project(project, ch, rules, dup_role, keep_name=None):
    """对单个项目返回 {green:[], yellow:[], red:[], uncat:[], total_kb}。
    全量记账：du 每个子项，规则不认识的大块进 uncat（❓未归类），不留隐形区。
    dup_role: 'keep' | 'archive' | 'solo'；keep_name=同组保留的最新版名。"""
    R = {"green": [], "yellow": [], "red": [], "protected_paths": [], "total_kb": 0}
    pname = os.path.basename(project)
    # finished_globs 为空(如外置盘归档) → 自动用"夹内是否已有成片"探测
    has_finished = (glob_hit(project, ch["finished_globs"]) if ch["finished_globs"]
                    else subtree_has_finished(project, rules))
    R["has_finished"] = has_finished

    # 记录受保护的成片/定稿绝对路径（硬保护，永不进 trash_paths）
    for f in find_matches(project, rules["protected_file_globs"]):
        R["protected_paths"].append(os.path.realpath(f))

    try:
        children = sorted(os.listdir(project))
    except PermissionError:
        return R

    min_kb = rules["min_report_mb"] * 1024
    uncat_kb_min = rules.get("uncat_min_mb", 300) * 1024
    misc_kb = 0  # 未归类的小碎片累计
    for name in children:
        cpath = os.path.join(project, name)
        if os.path.islink(cpath) or name.startswith("."):
            continue
        is_dir = os.path.isdir(cpath)
        kb = du_kb(cpath)          # 全量记账：每个子项都 du
        R["total_kb"] += kb

        # 🔴 受保护目录/文件 → 必留（已记账，不给按钮）
        if is_dir and name in rules["protected_dirs"]:
            continue
        if (not is_dir) and match_any(name, rules["protected_file_globs"]):
            R["red"].append({"name": "%s / %s" % (pname, name), "path": cpath,
                             "size": human(kb),
                             "why_keep": "成片/定稿，本工具硬保护，永不删。",
                             "indirect_release": "如需下线，请手动确认后自行处理。"})
            R["protected_paths"].append(os.path.realpath(cpath))
            continue

        # 死重量垃圾（旧版_不要使用 等）→ 无条件 🟢
        if match_any(name, rules["junk_names"]):
            if kb < 1024:
                continue
            R["green"].append(_green_item(pname, name, cpath, kb,
                              "已标记废弃（%s），死重量，可直接回收。" % name, bucket="junk"))
            continue

        # 🟢 中间产物目录
        if is_dir and (name in rules["intermediate_dirs"]
                       or match_any(name, rules["intermediate_dirs"])):
            if kb < min_kb:
                continue
            if has_finished:
                R["green"].append(_green_item(pname, name, cpath, kb,
                                  "中间产物；本期已出成片，删后可重跑 pipeline 再生。", bucket="bulk"))
            else:
                # 未出成片 → 不敢删，降级为需人工
                R["yellow"].append({"name": "%s / %s" % (pname, name), "path": cpath,
                    "size": human(kb), "bucket": "bulk",
                    "content_profile": "中间产物（%s）" % name,
                    "why_manual": "本期【未检测到成片】，删了可能白跑一轮，需你确认是否已发布/已废弃。",
                    "disposal": "确认已出片或已弃 → 移废纸篓；否则先出片。",
                    "risk": "未出片就删=素材白做，务必先确认。"})
            continue

        # 🟢 中间产物散文件（顶层 preview/临时/副本 等）
        if (not is_dir) and match_any(name, rules["intermediate_file_globs"]):
            if kb < min_kb:
                continue
            R["green"].append(_green_item(pname, name, cpath, kb,
                              "过程/预览/副本文件，可回收。", bucket="junk"))
            continue

        # ❓ 规则不认识的大块 → 先递归钻进去拆成片/中间产物，钻不出结果才落未归类台
        if kb >= uncat_kb_min:
            label = "%s / %s" % (pname, name)
            if is_dir:
                sub, hit = drill(label, cpath, rules, rules.get("drill_depth", 3))
                if hit:
                    R["green"] += sub["green"]; R["yellow"] += sub["yellow"]
                    R["red"] += sub["red"]; R["protected_paths"] += sub["protected_paths"]
                else:
                    R["yellow"].append(_uncat_item(label, cpath, kb, is_dir))
            else:
                R["yellow"].append(_uncat_item(label, cpath, kb, is_dir))
        else:
            misc_kb += kb
    R["misc_kb"] = misc_kb

    # 🟢 嵌套子路径中间产物（如 audio/tts）
    for sub in rules.get("intermediate_subpaths", []):
        sp = os.path.join(project, sub)
        if os.path.isdir(sp) and not os.path.islink(sp):
            kb = du_kb(sp)
            if kb >= min_kb and has_finished:
                R["green"].append(_green_item(pname, sub, sp, kb,
                                  "分句 TTS 中间音频，可回收。", bucket="bulk"))

    # 🔁 判重：同题旧版整期 → 复制件回收台（bucket=dup），默认移废纸篓可逆
    if dup_role == "archive":
        kb = du_kb(project)
        R["green"].append(_green_item(pname, "整期旧版", project, kb,
            "同题多版本中的较旧一份，最新版为「%s」。合并=删这份旧的、留最新。" % (keep_name or "最新版"),
            bucket="dup", extra={"keep_name": keep_name or "", "is_whole_project": True}))
    return R


def _green_item(pname, label, path, kb, note, bucket="bulk", extra=None):
    it = {
        "name": "%s / %s" % (pname, label),
        "project": pname,
        "path": path,
        "size_estimate": human(kb),
        "size_kb": kb,
        "bucket": bucket,        # dup=复制件/重复旧版  junk=死重量垃圾  bulk=已出成片的大宗中间产物
        "kill_processes": [],
        "trash_paths": [path],
        "commands": [{"label": "移到废纸篓（推荐，可逆）",
                      "cmd": "mv %s ~/.Trash/" % _q(path)}],
        "note": note,
    }
    if extra:
        it.update(extra)
    return it


def _q(p):
    return "'" + p.replace("'", "'\\''") + "'"


def system_info():
    info = {"os": "macOS " + _run(["sw_vers", "-productVersion"]).strip(),
            "build": _run(["sw_vers", "-buildVersion"]).strip(),
            "arch": _run(["uname", "-m"]).strip(),
            "user": os.environ.get("USER", ""),
            "home": os.path.expanduser("~"), "filesystem": "APFS", "purgeable": ""}
    try:
        t, u, f = shutil.disk_usage("/")
        info["disk_total"] = human(t // 1024)
        info["disk_used"] = human(u // 1024)
        info["disk_free"] = human(f // 1024)
    except Exception:
        info["disk_total"] = info["disk_used"] = info["disk_free"] = "?"
    info["disk_name"] = "Macintosh HD"
    info["disks"] = [{"name": "Macintosh HD", "total": info["disk_total"],
                      "used": info["disk_used"], "free": info["disk_free"]}]
    return info


def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return ""


# ======================================================================
# 通用磁盘维度（移植卡兹克 storage-analyzer 的扫描目标：真正占空间的大头）
# 开发缓存 / 浏览器缓存 / 下载堆积 / 大应用。删不删交给用户，我们负责扫出来。
# ======================================================================
HOME = os.path.expanduser("~")

DEV_CACHE_PATHS = [
    "~/Library/Caches/pip", "~/Library/Caches/uv", "~/.cache", "~/.cargo",
    "~/.npm", "~/.pnpm-store", "~/.gradle", "~/.m2", "~/Library/pnpm",
    "~/Library/Developer/Xcode/DerivedData", "~/Library/Developer/CoreSimulator",
    "~/Library/Developer/Xcode/iOS DeviceSupport", "~/go/pkg", "~/.docker",
    "~/Library/Caches/Homebrew", "~/Library/Caches/ms-playwright",
    "~/Library/Caches/huggingface", "~/.ollama/models",
]
BROWSER_CACHE_PATHS = [
    "~/Library/Caches/Google/Chrome", "~/Library/Caches/com.apple.Safari",
    "~/Library/Caches/Firefox", "~/Library/Caches/com.microsoft.edgemac",
    "~/Library/Caches/BraveSoftware",
]


def _du_item(path, kb, bucket, note, tier="green", extra=None):
    disp = path.replace(HOME, "~")
    base = {"name": disp, "path": path, "bucket": bucket, "note": note,
            "size_kb": kb, "channel": "系统/通用"}
    if tier == "green":
        base.update({"size_estimate": human(kb), "kill_processes": [],
                     "trash_paths": [path],
                     "commands": [{"label": "移到废纸篓（可逆）", "cmd": "mv %s ~/.Trash/" % _q(path)}]})
    else:  # yellow：需判断，只给"打开"，不给一键删
        base.update({"size": human(kb), "content_profile": note,
                     "why_manual": "占空间大但含你可能要用的数据，删不删你定。",
                     "disposal": "在访达打开审查后自行处理。",
                     "risk": "确认不再需要再清。"})
    if extra:
        base.update(extra)
    return base


def generic_disk_scan(rules):
    """扫通用磁盘大头，返回 (green[], yellow[])。全部只读 du。"""
    min_kb = rules.get("generic_min_mb", 200) * 1024
    green, yellow = [], []

    def scan_group(paths, bucket, note, tier="green"):
        out = []
        for p in paths:
            path = os.path.expanduser(p)
            if not os.path.isdir(path) or os.path.islink(path):
                continue
            kb = du_kb(path)
            if kb < min_kb:
                continue
            out.append(_du_item(path, kb, bucket, note, tier))
        return out

    log("[通用] 扫开发缓存…")
    green += scan_group(DEV_CACHE_PATHS, "cache",
                        "开发缓存，删了工具下次自动重建，可安全回收。")
    log("[通用] 扫浏览器缓存…")
    green += scan_group(BROWSER_CACHE_PATHS, "cache",
                        "浏览器缓存，删了自动重建（不影响登录/书签）。")

    # 下载堆积：大文件逐个列（需判断）
    log("[通用] 扫下载堆积…")
    dl = os.path.join(HOME, "Downloads")
    if os.path.isdir(dl):
        for name in sorted(os.listdir(dl)):
            cp = os.path.join(dl, name)
            if os.path.islink(cp) or name.startswith("."):
                continue
            kb = du_kb(cp)
            if kb >= min_kb:
                yellow.append(_du_item(cp, kb, "big",
                              "下载文件夹里的大项，多为一次性文件，确认没用可清。", "yellow"))

    # 大应用：/Applications 里的大 .app（需判断，只给打开去卸载）
    log("[通用] 扫大应用…")
    for base in ("/Applications", os.path.join(HOME, "Applications")):
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if not name.endswith(".app"):
                continue
            cp = os.path.join(base, name)
            if os.path.islink(cp):
                continue
            kb = du_kb(cp)
            if kb >= min_kb * 2:  # 应用门槛更高（400MB+）
                yellow.append(_du_item(cp, kb, "app",
                              "占空间较大的应用，确认不用可正规卸载。", "yellow"))
    return green, yellow


def main():
    started = time.time()
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CFG
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    rules = cfg["rules"]
    channels = cfg["channels"]

    green, yellow, red, protected = [], [], [], set()
    total_projects = 0
    accounted_kb = 0  # 全量记账：所有被 du 过的字节

    for ci, ch in enumerate(channels, 1):
        projects = list_projects(ch)
        log("[%d/%d] %s：%d 个项目" % (ci, len(channels), ch["name"], len(projects)))
        # 频道级判重
        groups = {}
        for p in projects:
            groups.setdefault(dup_key(os.path.basename(p), rules), []).append(p)
        role, keep_of = {}, {}
        for key, ps in groups.items():
            if len(ps) > 1:
                ps_sorted = sorted(ps)  # 时间戳后缀 → 字典序≈时间序，最后一个最新
                newest = os.path.basename(ps_sorted[-1])
                for p in ps_sorted[:-1]:
                    role[p] = "archive"
                    keep_of[p] = newest
                role[ps_sorted[-1]] = "keep"
            else:
                role[ps[0]] = "solo"

        for pi, project in enumerate(projects, 1):
            total_projects += 1
            log("    (%d/%d) %s" % (pi, len(projects), os.path.basename(project)))
            r = classify_project(project, ch, rules, role.get(project, "solo"),
                                 keep_name=keep_of.get(project))
            for g in r["green"]:
                g["channel"] = ch["name"]
                green.append(g)
            yellow += r["yellow"]
            red += r["red"]
            protected.update(r["protected_paths"])
            accounted_kb += r.get("total_kb", 0)

    # sweep_roots：频道之外的顶层散落物（下载/未命名/散文件/课程包），不留盘面死角
    ch_roots = {os.path.realpath(expand(c["root"])) for c in channels}
    uncat_kb_min = rules.get("uncat_min_mb", 300) * 1024
    for sr in cfg.get("sweep_roots", []):
        sroot = expand(sr)
        if not os.path.isdir(sroot):
            continue
        log("[sweep] %s" % sroot)
        try:
            entries = sorted(os.listdir(sroot))
        except PermissionError:
            continue
        for name in entries:
            sp = os.path.join(sroot, name)
            if name.startswith(".") or os.path.islink(sp):
                continue
            if os.path.realpath(sp) in ch_roots:
                continue  # 频道目录已扫，不重复记账
            if name in ("System Volume Information",):
                continue
            kb = du_kb(sp)
            accounted_kb += kb
            if kb < uncat_kb_min:
                continue
            yellow.append({"name": "盘面散落 / %s" % name, "path": sp,
                "size": human(kb), "bucket": "uncat",
                "content_profile": "频道目录之外的顶层%s" % ("目录" if os.path.isdir(sp) else "文件"),
                "why_manual": "不属于任何频道项目，占着 %s。打开确认是什么再决定。" % human(kb),
                "disposal": "在访达打开确认 → 没用移废纸篓；有用就归位到对应频道目录。",
                "risk": "删前确认不是唯一副本。"})

    # 通用磁盘维度（卡兹克那套真正的空间大头）；扫外置盘等场景可用 skip_generic 跳过本地缓存
    if not cfg.get("skip_generic"):
        gen_green, gen_yellow = generic_disk_scan(rules)
        green += gen_green
        yellow += gen_yellow

    # 开箱安检：绿灯目录发放前查内部是否藏成片/定稿文件（如 veo_clips/opening_final.mp4），
    # 命中一律降级🟡。只查内容类 bucket（bulk/junk/dup），系统缓存不查（文件海量且非用户内容）。
    # 安检模式取"配置保护名 ∪ 宽版兜底"——opening_final.mp4 这类中缀命名也要拦住
    prot_base = list({os.path.basename(p) for p in rules["protected_file_globs"]}
                     | {"*final*.mp4", "*成片*.mp4", "*定稿*.*", "*完整合成*.mp4", "*最终版*.mp4"})

    def dir_contains_protected(path, cap=8000):
        n = 0
        try:
            for root, _dirs, files in os.walk(path):
                for f in files:
                    n += 1
                    if n > cap:
                        return None  # 太大查不完 → 保守视为可疑
                    if match_any(f, prot_base):
                        return os.path.join(root, f)
        except OSError:
            return None
        return ""  # 干净

    checked_green = []
    for g in green:
        if g.get("bucket") not in ("bulk", "junk", "dup"):
            checked_green.append(g)
            continue
        suspicious = None
        for tp in g.get("trash_paths", []):
            if os.path.isdir(tp):
                hit = dir_contains_protected(tp)
                if hit != "":
                    suspicious = hit or "(目录过大未能全查)"
                    break
        if suspicious:
            yellow.append({"name": g["name"], "path": g["path"],
                "size": g.get("size_estimate", ""), "bucket": g.get("bucket", "bulk"),
                "content_profile": "中间产物目录，但内部发现疑似成片/定稿：%s" % suspicious,
                "why_manual": "整夹删除会连带删掉这个疑似成片文件，需你确认它是否重要。",
                "disposal": "在访达打开确认 → 该文件重要就先挪走，再清整夹。",
                "risk": "宁可多点一次，不赌成片。"})
            log("！绿降黄(内藏疑似成片): %s" % g["path"])
        else:
            checked_green.append(g)
    green = checked_green

    # 安全兜底：任何被保护路径若不慎出现在某个 trash_paths，剔除该 green 项
    safe_green = []
    for g in green:
        if any(os.path.realpath(tp) in protected for tp in g.get("trash_paths", [])):
            log("！跳过疑似受保护项：%s" % g["path"])
            continue
        safe_green.append(g)
    green = safe_green

    green.sort(key=lambda x: x.get("size_kb", 0), reverse=True)
    g_gb = sum(gb(x.get("size_kb", 0)) for x in green)
    y_gb = sum(gb(du_kb(y["path"])) for y in yellow) if False else 0.0
    # yellow 体量已在各项 size 里，汇总用解析
    def _p(s):
        m = re.search(r"([\d.]+)\s*(GB|MB)", s or "")
        if not m:
            return 0.0
        v = float(m.group(1))
        return v if m.group(2) == "GB" else v / 1024
    y_gb = sum(_p(y.get("size", "")) for y in yellow)
    r_gb = sum(_p(x.get("size", "")) for x in red)

    # 按 bucket 汇总（回收厂头版：谁占得大谁排前）
    BUCKET_META = {
        "cache": ("💾", "开发/浏览器缓存", "删了自动重建，最安全的大头"),
        "junk": ("🗑", "死重量垃圾", "废弃/失败渲染/临时/副本，零犹豫"),
        "dup": ("🔁", "重复件·旧版", "同题多版本，合并留最新"),
        "bulk": ("🎬", "内容中间产物", "已出成片项目的 clips/图，可再生"),
        "big": ("📦", "下载/大文件", "占空间的一次性文件，你定"),
        "app": ("📥", "大应用", "确认不用可正规卸载"),
        "uncat": ("❓", "未归类大块", "规则不认识但确实占空间，打开看一眼再定"),
    }
    bucket_gb = {}
    for g in green:
        bucket_gb[g.get("bucket", "bulk")] = bucket_gb.get(g.get("bucket", "bulk"), 0) + gb(g.get("size_kb", 0))
    for y in yellow:
        b = y.get("bucket", "big")
        bucket_gb[b] = bucket_gb.get(b, 0) + _p(y.get("size", ""))
    buckets = [{"key": k, "icon": BUCKET_META.get(k, ("📁", k, ""))[0],
                "label": BUCKET_META.get(k, ("📁", k, ""))[1],
                "hint": BUCKET_META.get(k, ("📁", k, ""))[2],
                "gb": round(v, 1)} for k, v in bucket_gb.items()]
    buckets.sort(key=lambda x: x["gb"], reverse=True)

    top5 = [{"rank": i + 1, "tier": "green", "size": g["size_estimate"],
             "type": BUCKET_META.get(g.get("bucket", "bulk"), ("", "", ""))[1],
             "name": g["name"], "path": g["path"],
             "note": g.get("note", "")} for i, g in enumerate(green[:5])]

    for g in green:
        g.pop("size_kb", None)

    trees = int((g_gb + y_gb) / 5)  # 每回收 5GB ≈ 种一棵树
    accounted_gb = gb(accounted_kb)
    summary = {
        "overview": "共盘点约 %.0f GB。可回收约 %.1f GB（绿灯闭眼可清）+ 需你判断约 %.1f GB（含❓未归类大块）。删不删你定，我只负责扫全、分级、一键可逆处置。"
                    % (accounted_gb, g_gb, y_gb),
        "accounted_gb": round(accounted_gb, 1),
        "reclaim_gb": round(g_gb, 1), "review_gb": round(y_gb, 1),
        "trees": trees, "total_projects": total_projects,
        "buckets": buckets,
        "tier_stats": {"green": "约 %.1f GB" % g_gb, "yellow": "约 %.1f GB" % y_gb,
                       "red": "约 %.1f GB" % r_gb},
        "priority": [
            "开发/浏览器缓存通常是最大且最安全的一坨，删了工具自动重建。",
            "死重量垃圾（旧版_不要使用/失败渲染/副本）零风险，直接清。",
            "重复件合并留最新；已发布项目的 clips/图是回收主力。",
            "大应用/大下载先在访达看一眼再决定。",
        ],
        "long_term": [
            "每期发布后跑一次，趁记得清中间产物。",
            "同题多时间戳项目定稿后只留最新。",
            "外置盘已 97% 满：归档前先清盘或扩容。",
        ],
    }

    data = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "scan_seconds": round(time.time() - started, 1),
        "system": system_info(),
        "top5": top5,
        "green": green,
        "yellow": yellow,
        "red": red,
        "denied": [],
        "summary": summary,
        "_protected_count": len(protected),
    }
    print(json.dumps(data, ensure_ascii=False, indent=2))
    log("完成：盘点%.0fGB · 绿 %d 项/约%.1fGB · 黄 %d 项/约%.1fGB · 红(保护) %d 项 · 耗时 %.1fs"
        % (accounted_gb, len(green), g_gb, len(yellow), y_gb, len(red), data["scan_seconds"]))


if __name__ == "__main__":
    main()
