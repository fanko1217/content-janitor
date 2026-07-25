#!/usr/bin/env python3
"""Regression test: live cache recreation must not block recording restore."""
import importlib.util
import os
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = importlib.util.spec_from_file_location(
    "janitor_server", os.path.join(HERE, "server.py")
)
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


def main():
    with tempfile.TemporaryDirectory(prefix="janitor-recording-restore-test-") as root:
        home = os.path.join(root, "home")
        original = os.path.join(home, "Library", "Caches", "Demo")
        os.makedirs(original, exist_ok=True)
        with open(os.path.join(original, "before.txt"), "w", encoding="utf-8") as f:
            f.write("before")

        SERVER.HOME = home
        SERVER.RECORDING_SESSION = "recording-test"
        SERVER.RECORDING_MOVES.clear()
        SERVER.RECORDING_DIRS.clear()
        SERVER._stage_for_recording(original)

        os.makedirs(original, exist_ok=True)
        with open(os.path.join(original, "during.txt"), "w", encoding="utf-8") as f:
            f.write("during")

        restored, errors = SERVER.restore_recording_moves()
        assert restored == 1, (restored, errors)
        assert not errors, errors
        assert open(os.path.join(original, "before.txt"), encoding="utf-8").read() == "before"
        assert open(os.path.join(original, "during.txt"), encoding="utf-8").read() == "during"

    print("PASS: 录屏期间重建的缓存不会阻断原位恢复")


if __name__ == "__main__":
    main()
