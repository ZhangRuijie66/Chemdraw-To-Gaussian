# -*- coding: utf-8 -*-
"""高斯计算工具 —— 启动入口。

    python run.py                 启动本地网页界面
    python run.py --test          命令行自检：扫 calculation 目录并生成 .gjf 到临时目录
    python run.py --make 输入目录 输出目录 [--functional PBE1PBE --basis def2TZVP ...]
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from gcalc import batch  # noqa: E402


def _default_input():
    """默认输入目录：上一层「3 紫外光谱搭建\\calculation」。"""
    cand = os.path.join(os.path.dirname(HERE), '3 紫外光谱搭建', 'calculation')
    return cand if os.path.isdir(cand) else ''


def run_test():
    # 先做一次接口自检：HpcClient 的方法被误删时能立刻发现
    from gcalc.hpc import HpcClient
    need = ['list_files', 'list_remote', 'run_formchk', 'download_files',
            'download_named', 'history', 'status', 'fetch_logs', 'submit',
            'upload_dir', 'is_alive', 'close', 'run', 'resolve_remote']
    missing = [n for n in need if not hasattr(HpcClient, n)]
    if missing:
        print('接口自检失败：HpcClient 缺少 %s' % ', '.join(missing))
        return 1
    print('接口自检通过（HpcClient 方法齐全）')

    src = _default_input()
    if not src:
        print('找不到默认数据目录，请用 --make 指定')
        return 1
    print('扫描 %s' % src)
    items = batch.scan(src)
    for it in items:
        if it['ok']:
            print('  %-8s %-18s 电荷=%+d 重原子=%2d 分子量=%.2f' %
                  (it['name'], it['formula'], it['charge'], it['heavy_atoms'], it['mol_wt']))
        else:
            print('  %-8s 失败：%s' % (it['name'], it['error']))

    cfg = batch.default_config()
    cfg['input_dir'] = src
    out = os.path.join(HERE, '_test_out')
    cfg['out_dir'] = out
    print('\n生成到 %s' % out)
    for it in items:
        if not it['ok']:
            continue
        try:
            res = batch.make_one(it['path'], cfg, write=True)
            print('  %-8s → %s  (%d 原子, %s 能量 %.2f kcal/mol)' %
                  (it['name'], os.path.basename(res['files'][0]), res['atoms'],
                   res['force_field'], res['energy']))
        except Exception as exc:  # noqa: BLE001
            print('  %-8s 生成失败：%s' % (it['name'], exc))
    print('\n完成。')
    return 0


def run_make(argv):
    if len(argv) < 2:
        print('用法：python run.py --make 输入目录 输出目录')
        return 2
    src, out = argv[0], argv[1]
    cfg = batch.default_config()
    cfg['input_dir'] = src
    cfg['out_dir'] = out
    opts = {'--functional': 'functional', '--basis': 'basis', '--job': 'job',
            '--solvent': 'solvent', '--nproc': 'nproc', '--mem': 'mem'}
    for i, a in enumerate(argv):
        if a in opts and i + 1 < len(argv):
            v = argv[i + 1]
            cfg[opts[a]] = int(v) if opts[a] == 'nproc' else v
    items = batch.scan(src)
    if not items:
        print('目录里没有 .cdxml/.cdx/.mol 文件')
        return 1
    results = batch.make_many([it['path'] for it in items if it['ok']], cfg)
    for r in results:
        if r.get('error'):
            print('  ✗ %-8s %s' % (r['name'], r['error']))
        else:
            print('  ✓ %-8s %s' % (r['name'], ', '.join(os.path.basename(f) for f in r['files'])))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if '--test' in argv:
        return run_test()
    if '--make' in argv:
        i = argv.index('--make')
        return run_make(argv[i + 1:])
    from gcalc import server
    return server.main(argv)


if __name__ == '__main__':
    sys.exit(main())
