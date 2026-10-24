#!/usr/bin/env python3
"""比对测试工作区里的标准脚本副本和 svc-local-test/kit 里的标准版本，见 ADR 0002。

  sync.py --workspace <服务>/testcase           列出不一致和缺失的文件，有就退出码 1
  sync.py --workspace <服务>/testcase --apply   用标准版本覆盖（缺的补上）

在技能目录里执行，不复制进工作区。
"""
import argparse
import filecmp
import os
import shutil
import sys

KIT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kit")


def kit_files():
    for root, dirs, files in os.walk(KIT):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), KIT)
            if not f.endswith(".pyc"):
                yield rel


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workspace", required=True)
    p.add_argument("--apply", action="store_true")
    a = p.parse_args()
    ws = os.path.abspath(a.workspace)
    diff = []
    for rel in sorted(kit_files()):
        src, dst = os.path.join(KIT, rel), os.path.join(ws, rel)
        if not os.path.exists(dst):
            diff.append(("缺失", rel))
        elif not filecmp.cmp(src, dst, shallow=False):
            diff.append(("不一致", rel))
    for state, rel in diff:
        print(f"{state}\t{rel}")
        if a.apply:
            dst = os.path.join(ws, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(KIT, rel), dst)
    if not diff:
        print("标准脚本一致")
    elif a.apply:
        print(f"已同步 {len(diff)} 个文件")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
