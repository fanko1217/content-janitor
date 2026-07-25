#!/usr/bin/env python3
"""Validate that a scan result and report template expose the three safety tiers.

Usage:
    validate_report.py <analysis.json>
"""
import json
import os
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "assets", "report_template.html")


def fail(message):
    print("验证失败：" + message, file=sys.stderr)
    raise SystemExit(1)


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)

    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)
    with open(TEMPLATE, encoding="utf-8") as f:
        template = f.read()

    required_tiers = ("green", "yellow", "red")
    for tier in required_tiers:
        if tier not in data or not isinstance(data[tier], list):
            fail("扫描结果缺少 %s 列表" % tier)

    stats = (data.get("summary") or {}).get("tier_stats") or {}
    for tier in required_tiers:
        if not stats.get(tier):
            fail("summary.tier_stats 缺少 %s 数字" % tier)

    markers = (
        "绿灯·闭眼可删",
        "黄灯·需要判断",
        "红灯·硬保护",
        "tier-green",
        "tier-yellow",
        "tier-red",
        "不进入删除白名单",
        "不能按体积隐藏分组",
        'id="confirmMask"',
        "askConfirm",
        "publicPath",
        "RECORDING",
        "/Volumes/外置盘/",
    )
    for marker in markers:
        if marker not in template:
            fail("报告模板缺少可见标记：" + marker)

    html = template.replace(
        "__REPORT_DATA__", json.dumps(data, ensure_ascii=False)
    ).replace("__DELETE_CONFIG__", "null")
    if "__REPORT_DATA__" in html or "__DELETE_CONFIG__" in html:
        fail("报告模板占位符没有替换完整")

    print(
        "三色报告验证通过：绿灯 %d 项，黄灯 %d 项，红灯 %d 项。"
        % (len(data["green"]), len(data["yellow"]), len(data["red"]))
    )


if __name__ == "__main__":
    main()
