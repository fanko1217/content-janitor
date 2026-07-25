#!/usr/bin/env python3
"""Regression check: protected project files must not imply a finished video."""

import importlib.util
import json
import os
import tempfile


HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = importlib.util.spec_from_file_location("janitor_scan", os.path.join(HERE, "scan.py"))
SCAN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCAN)


def touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb"):
        pass


def main():
    config_path = os.path.join(HERE, "..", "channels.example.json")
    with open(config_path, encoding="utf-8") as f:
        rules = json.load(f)["rules"]

    with tempfile.TemporaryDirectory(prefix="janitor-finished-gate-") as root:
        touch(os.path.join(root, "project.json"))
        touch(os.path.join(root, "project_config.json"))
        touch(os.path.join(root, "文稿定稿.txt"))
        os.makedirs(os.path.join(root, "clips"))

        assert not SCAN.subtree_has_finished(root, rules), (
            "project.json / 配置 / 定稿文稿不能证明已经出成片"
        )

        touch(os.path.join(root, "交付", "正式版", "final_release.mp4"))
        assert SCAN.subtree_has_finished(root, rules), "明确成片视频应触发完成门"

        os.remove(os.path.join(root, "交付", "正式版", "final_release.mp4"))
        touch(os.path.join(root, "交付", "正式版", "._成片.mp4"))
        assert not SCAN.subtree_has_finished(root, rules), "AppleDouble 影子文件不能触发完成门"

    print("成片保险丝验证通过：工程文件不触发绿灯，明确成片视频才触发。")


if __name__ == "__main__":
    main()
