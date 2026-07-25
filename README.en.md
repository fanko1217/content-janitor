# ♻️ Content Janitor

> Turn disk cleanup into an Ant-Forest game — **scan the real space hogs, collect energy orbs, grow a tree.**

[中文](README.md) · **English**

[![License](https://img.shields.io/badge/License-MIT-3B82F6?style=for-the-badge)](./LICENSE)
[![Python 3](https://img.shields.io/badge/Python_3-zero_deps-10B981?style=for-the-badge&logo=python&logoColor=white)](#quick-start-macos)
[![Agent Skill](https://img.shields.io/badge/Agent_Skill-Standard-8B5CF6?style=for-the-badge)](#)

![macOS](https://img.shields.io/badge/macOS-tested-000000?style=flat-square&logo=apple&logoColor=white)
![Claude Code](https://img.shields.io/badge/Claude_Code-Skill-D97706?style=flat-square&logo=anthropic&logoColor=white)
![Codex](https://img.shields.io/badge/Codex-Skill-10B981?style=flat-square&logo=openai&logoColor=white)
![Read-only scan](https://img.shields.io/badge/scan-read--only-brightgreen?style=flat-square)

An open-source **Agent Skill / standalone script** that read-only scans your whole machine for what actually eats disk, groups it into "recycling stations", and lets you **clean it up in one click** through a healing Ant-Forest webpage. Works with Claude Code, Codex, and other Agent-Skills tools — or run it as a plain Python script.

<p align="center">
  <img src="docs/screenshot.png" width="780" alt="Content Janitor — Ant-Forest style cleanup report">
</p>

## ✨ Highlights

- **🎮 Cleanup = growing a tree** — reclaimable items become glowing **energy orbs**; tap to collect → orb flies in → particles burst → the central tree grows (🌱→🌿→🌳→blossom).
- **🔍 Finds the real space hogs** — dev caches (`~/.cache`, pip/npm/Xcode, often tens of GB), browser caches, big downloads, big apps — not just a few hundred MB of system cache.
- **🧾 Full accounting, zero blind spots** — every byte is accounted for: unknown big folders get **recursively drilled** (`drill_depth`) to split finals from intermediates, the rest lands in a "❓ uncategorized" station; the report's "total audited X GB" reconciles against disk usage (99% coverage in practice).
- **🎬 A creator dimension no one else has** — intermediate files from video/editing projects (clips, image sequences, render temp), duplicate old versions, failed renders. Built for content creators and developers.
- **🔒 Safety first, you decide** — **read-only** scanning; important files (final videos, master docs) are **hard-protected, never deleted**; local server + path allowlist + random token + `127.0.0.1` only; **no network, no upload, no telemetry**. "Move to Trash" (reversible) is the default.
- **🎵 Healing ambient audio** — Web Audio generated soft rain + wind-chime (toggleable).
- **🧩 Zero third-party deps** — pure Python 3 stdlib + a single HTML file, works offline. macOS out of the box.

## 🎯 What it solves

Your disk keeps filling up, but you **don't know what's eating it** and don't dare delete blindly. It does three things: **① Scan everything** (generic disk hogs + content-project leftovers) → **② Grade** (🟢 safe to clean / 🟡 your call / 🔴 protected) → **③ One-click reversible cleanup**. Deleting is always your decision; the tool just puts everything worth seeing in front of you.

## 🚀 Quick Start (macOS)

```bash
git clone https://github.com/fanko1217/content-janitor.git
cd content-janitor

cp channels.example.json channels.json   # optional: point it at your project folders
python3 scripts/scan.py > /tmp/janitor_analysis.json
python3 scripts/server.py /tmp/janitor_analysis.json   # opens the Ant-Forest report; Ctrl+C to stop
```

`finished_globs` is the safety fuse for creator projects: intermediates turn
green only when an explicit final-video pattern matches. If it is left empty for
an archive drive, conservative `auto_finished_globs` rules look only for clear
final-video files. Protected project files such as `project.json`, config files,
and master text remain red, but never count as proof that a final exists.

> **As an Agent Skill**: drop this repo into `~/.claude/skills/` and tell Claude Code / Codex `clean my disk` / `what's eating my storage`.

## 🗂 Recycling Stations

| Station | What | Verdict |
|---|---|---|
| 💾 Dev / browser caches | pip/npm/uv/Xcode/`~/.cache`/Chrome cache | 🟢 auto-rebuilt |
| 🗑 Dead weight | discarded markers, failed renders, temp/copies | 🟢 no-brainer |
| 🔁 Duplicates / old versions | same-title multi-version projects | 🟢 keep latest |
| 🎬 Content intermediates | clips/images of finished projects | 🟢 regenerable |
| 📦 Big downloads | large files in Downloads | 🟡 your call |
| 📥 Big apps | large apps in `/Applications` | 🟡 your call |
| 🔒 Finals / masters | final videos, master docs, sources | 🔴 hard-protected, no delete button |

## 🔒 Safety Model

Read-only scan; a two-layer red line keeps protected paths out of any delete allowlist; local server binds `127.0.0.1` + random port + token + Host check; every delete asks for browser confirmation; reversible "Move to Trash" is the default.

## 🙏 Credits

The four-stage skeleton (read-only scan → grade → interactive report → guarded one-click action) learns from and credits **[Khazix · storage-analyzer](https://github.com/KKKKhazix/khazix-skills)** (MIT). This project adds a **content-creator dimension** and an **Ant-Forest gamified** presentation.

## 📄 License

MIT © 2026 fanko
