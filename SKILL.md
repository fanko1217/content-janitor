---
name: fanko-content-janitor
description: >
  内容回收厂——扫出 fanko 整台电脑真正占空间的垃圾并一键回收的清理系统（学卡兹克
  storage-analyzer 骨架 + 内容资产维度合流）。只读扫描【通用磁盘大头】(开发缓存 pip/npm/Xcode、
  浏览器缓存、大下载、大应用) + 【内容维度】(各频道项目的 clips/图中间产物、重复旧版、死重量)，
  按回收台分类：💾缓存 🗑死垃圾 🔁重复件 🎬内容中间产物 📦大下载 📥大应用，谁占得大谁排头条。
  删不删【交给用户定】——本工具负责扫全+三色分级+一键可逆处置(移废纸篓)。呈现为「回收厂」
  游戏化 HTML（暖色/种树进度/投进回收站，和卡兹克后台风彻底区别）。成片/定稿硬保护永不删。
  务必在以下场景使用：fanko 说"清理电脑/磁盘满了/清出空间/扫垃圾/哪些能删/清缓存/清项目/
  清 clips/内容清道夫/回收厂/清一下 literary/宠物"，或抱怨电脑没空间、想知道什么在吃硬盘时。
---

# 内容回收厂 fanko-content-janitor

学卡兹克 storage-analyzer 四段式骨架（**只读扫描 → 机械分级 → 回收厂报告 → 守卫式处置**）。
**范围= 通用磁盘真垃圾（卡兹克维度）+ fanko 内容资产维度（差异化）**，合流成一台"电脑真垃圾全景扫描器"。
删不删交给 fanko 定，工具只负责扫全、分级、一键可逆回收。

## 铁律（对齐 fanko CLAUDE.md）

- **只读扫描。** scan.py 只跑 `du`/`listdir`/`glob`，绝不写。分级是机械规则，不靠猜。
- **成片零误删（最高红线）。** 成片/定稿的绝对路径进 `PROTECTED` 集合，`scan.py` 结尾兜底剔除任何混入 `trash_paths` 的受保护路径；`server.py` 只接受 green `trash_paths` 白名单内、且在 `$HOME` 下的路径。两层防线。
- **默认移废纸篓，不直接删。** 创作资产比缓存金贵——废纸篓可逆优先，"直接删"是次选。
- **未检测到成片 → 一律降级 🟡**，绝不 green。宁可让 fanko 多确认一次，不赌。
- **归档前查挂载 + 查空间**（阶段二）：外置盘已 97% 满，`[ -d "$EXT" ]` 未挂载即停、`df` 空间不足即停。Remotion `public/` 不能软链（会图裂），归档时排除。
- **每次处置追加写清理日志**，复用 fanko 已有 `清理日志_YYYY-MM-DD.md` 的"保留/删除/释放GB"格式，可追溯（断点存档）。

## 执行流程

### Step 1 只读扫描
```bash
python3 scripts/scan.py > /tmp/janitor_analysis.json   # 进度打到 stderr
```
`scan.py` 读同级 `../channels.json`（频道注册 + 分级规则），逐频道枚举项目，机械分级，输出
report-ready 的 analysis JSON。全 5 频道 ~4-5s。

### Step 2 Claude 复核（可选但推荐）
读 `/tmp/janitor_analysis.json`，人工/Claude 复核边界项：
- 🟡 里"未检测到成片"的项目——若你知道它已发布（成片已移外置盘），可手动上调该项 `clips` 到 green。
- 🔴 抽查：每期成片是否都被正确识别（尤其成片放在**项目根**而非 output/ 的项目）。

### Step 3 生成交互报告（默认服务模式，可一键处置）
```bash
python3 scripts/validate_report.py /tmp/janitor_analysis.json  # 三色分级验收，失败就停止
python3 scripts/server.py /tmp/janitor_analysis.json   # 127.0.0.1+随机端口+随机token，自动开浏览器，Ctrl+C 停

# 公开教程录屏：隐藏个人路径，并使用没有标签栏、地址栏、书签栏的独立窗口
JANITOR_PUBLIC_OUTPUT=1 python3 scripts/scan.py > /tmp/janitor_analysis.json
python3 scripts/validate_report.py /tmp/janitor_analysis.json
python3 scripts/server.py /tmp/janitor_analysis.json --recording-mode
```
页面首屏和正文必须明确出现：`绿灯·闭眼可删`、`黄灯·需要判断`、`红灯·硬保护`。
🟢 给「移废纸篓 / 直接删」+分组「全部移废纸篓」；🟡 逐项判断；🔴 无删除按钮（保护，仅供核对）。

仅要只读留存报告时用静态模式（无删除能力）：
```bash
python3 scripts/build_report.py /tmp/janitor_analysis.json ~/Desktop/内容清道夫_报告.html && open ~/Desktop/内容清道夫_报告.html
```

### Step 4 对话给结论
报告开后，一段话结论先行：可直接回收多少、最该先清的 2-3 项、需你判断的有哪些。细节看网页。

### Step 5 公开录屏验收

- 首屏必须同时看到三色名称和数字，正文必须有三个独立分区。
- 公开录屏一律使用 `--recording-mode`；不得录入标签栏、地址栏、书签、桌面图标和私人页面。
- 路径必须显示为 `~` 或 `/Volumes/外置盘/…/文件名`，不能出现用户名、盘名和完整目录。
- 删除确认必须使用页面正中弹窗；黄灯逐项判断；红灯只展示保护、绝不操作。
- 录屏模式下的回收动作会先暂存真实文件，停止服务时必须看到“已还原”结果。
- 录完抽查关键帧：三色总览、三个正文分区、居中确认框、能量球飞入、树成长。

## 回收台分类（bucket，scan.py 机械判定 + 前端按体积排序）

**通用磁盘维度（卡兹克那套真正的空间大头，scan.py `generic_disk_scan`）**：
- 💾 `cache` 开发/浏览器缓存（pip/npm/uv/Xcode DerivedData/.cache/Chrome 缓存等）→ 🟢可删（删了自动重建）
- 📦 `big` Downloads 里的大文件 → 🟡需判断（只给"在访达打开"）
- 📥 `app` `/Applications` 大应用 → 🟡需判断（打开去正规卸载）

**内容资产维度（差异化，classify_project）**：
- 🎬 `bulk` 已出成片项目的 `clips/`/`images/`/`audio/tts` → 🟢可删（可重跑再生，**前提=本期已检测到成片**）
- 🗑 `junk` 死重量：`旧版_不要使用*`、失败渲染、`*_preview.mp4`、`temp-*`、`*_副本.*` → 🟢可删
- 🔁 `dup` 同题多时间戳的旧版整期 → 🟢"合并·留最新"（默认移废纸篓可逆）
- 未检测到成片的 `clips/` → 🟡需判断（可能白跑一轮，不给一键删）
- 🔴 成片/定稿硬保护：各频道成片（见下表）、`*定稿*.txt`、`script/` `data/` `stage0/`、封面、`project.json`

改扫描目标/门槛 → 改 `channels.json`（通用维度路径在 scan.py `DEV_CACHE_PATHS`/`BROWSER_CACHE_PATHS`）。

## 成片定位（因项目结构而异，误删风险最高，全在 channels.json）

「一期是否已出成片」由每个频道的 `finished_globs` 判定——成片存在，其中间产物(clips/图)才允许进 🟢 可删；没检测到成片就降 🟡 让你确认，绝不赌。不同项目成片放的位置不同，配置示例：

**保险丝规则**：受保护不等于已经出成片。`project.json`、工程配置和定稿文稿
只能进入红灯保护，不能触发中间产物进绿灯。`finished_globs` 留空时，只允许
`auto_finished_globs` 中的明确成片视频触发绿灯。

| 结构类型 | `layout` | 成片规则 `finished_globs` 举例 |
|---|---|---|
| 每期在 `projects/` 下、成片在 output/ | `projects` | `["output/final*.mp4"]` |
| 每期在 `projects/` 下、成片在**项目根** | `projects` | `["*final*.mp4"]`（⚠️不在 output/） |
| 每期是顶层文件夹 | `flat` | `["preview_*.mp4", "output/*.mp4"]` |

改扫描目标/新增频道 → 改 `channels.json`（复制自 `channels.example.json`），不改脚本。

## 阶段状态

- **阶段一（已跑通）**：通用磁盘+内容维度合流扫描 + bucket 机械分级 + 回收厂游戏化报告 + 移废纸篓/删。全盘验证：可回收 26GB 绿+62GB 需判断，成片零误删红线通过，`~/.cache` 16.9GB 等真大头扫出。
- **阶段二（待做）**：`archive_to_ext.sh` 归档外置盘+留软链（挂载/空间安全门、排除 Remotion public/）、清理日志 `清理日志_YYYY-MM-DD.md` 落盘。
- **阶段三（待做）**：zip 交付打包清源、跨盘/跨项目真·重复文件(hash)去重、Windows 适配。
- **蚂蚁森林游戏化已内置**：清新蓝绿天 + 会长大的 emoji 真树(🌱→🌿→🌳→开花，按已回收GB 5阶段) + 悬浮能量球点击收集(飞入+粒子+树成长) + Web Audio 疗愈环境音(棕噪柔雨+水滴风铃，右上角开) + 回收台按体积排序。删后前端实时刷新可回收数字与净化进度。**每项一键直接删**(投废纸篓可逆/直接删)，成片保护区无删按钮。

## 依赖
Python 3 标准库，零第三方。macOS 自带 `du`/`osascript`。改配置只动 `channels.json`。
