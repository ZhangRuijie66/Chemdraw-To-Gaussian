# -*- coding: utf-8 -*-
"""打包便携版：把工具 + 启动器 + 使用说明 打成一个 zip。

    python make_portable.py [输出目录]

默认输出到 ../发布/高斯计算工具-可移植版.zip。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = '高斯计算工具-可移植版'
SKIP_DIRS = {'__pycache__', '_test_out', '.git'}
SKIP_FILES = {'settings.json', 'make_portable.py'}
SKIP_PREFIX = ('.dsh-ops-update',)


def copy_tool(dst):
    os.makedirs(dst, exist_ok=True)
    for fn in os.listdir(HERE):
        if fn in SKIP_DIRS or fn in SKIP_FILES or fn.startswith(SKIP_PREFIX):
            continue
        src = os.path.join(HERE, fn)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dst, fn),
                            ignore=lambda d, names: [n for n in names
                                                     if n in SKIP_DIRS])
        else:
            shutil.copyfile(src, os.path.join(dst, fn))


def main(argv):
    out_dir = argv[1] if len(argv) > 1 else os.path.join(
        os.path.dirname(HERE), '发布')
    os.makedirs(out_dir, exist_ok=True)
    stage = os.path.join(out_dir, '_stage_pkg', NAME)
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    os.makedirs(stage)

    copy_tool(os.path.join(stage, '高斯计算工具'))
    shutil.copyfile(os.path.join(stage, '高斯计算工具', 'docs', '使用说明-便携版.md'),
                    os.path.join(stage, '使用说明.md'))
    shutil.copyfile(os.path.join(stage, '高斯计算工具', 'tools', '启动-便携版.cmd'),
                    os.path.join(stage, '启动.cmd'))

    # 便携版用出厂设置
    example = os.path.join(stage, '高斯计算工具', 'settings.example.json')
    shutil.copyfile(example, os.path.join(stage, '高斯计算工具', 'settings.json'))

    zip_path = os.path.join(out_dir, NAME + '.zip')
    if os.path.exists(zip_path):
        os.remove(zip_path)
    n = 0
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dirpath, dirnames, filenames in os.walk(stage):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                if fn.endswith('.pyc'):
                    continue
                full = os.path.join(dirpath, fn)
                z.write(full, os.path.join(NAME, os.path.relpath(full, stage)))
                n += 1
    print('已生成：%s（%d 个文件，%.1f MB）'
          % (zip_path, n, os.path.getsize(zip_path) / 1048576))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
