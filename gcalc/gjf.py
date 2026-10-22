# -*- coding: utf-8 -*-
"""Gaussian 输入文件（.gjf）的写出。

格式照用户 2026-10-21 给的模板 A1-2.gjf：
    %nprocshared=32
    %mem=160GB
    %chk=A1_opt.chk
    #p opt freq PBE1PBE/def2TZVP EmpiricalDispersion=GD3BJ Int=(UltraFine,NoXCTest) SCF=NoVarAcc

    A1

    1 1
     C                 -5.60934000   -0.28220000   -1.24457000
     ...
    （最后留两个空行）

坐标行格式实测为 '%2s%28.8f%14.8f%14.8f'（用 A1-2.gjf 逐字对齐验证过），
元素符号右对齐占 2 列，每个坐标 14 列宽、8 位小数。
"""
from __future__ import annotations

import io
import os

COORD_FMT = '%2s%28.8f%14.8f%14.8f'
NL = chr(10)        # 避免源码里出现转义换行


def format_atom(symbol, x, y, z):
    return COORD_FMT % (symbol, x, y, z)


def build_gjf(name, atoms, charge=0, multiplicity=1, cfg=None):
    """atoms: [(symbol, x, y, z), ...]（Å）。

    cfg 可含：nproc, mem_mb, chk, route, title, trailing_blank_lines, comments
    """
    cfg = dict(cfg or {})
    nproc = int(cfg.get('nproc') or 32)
    mem = cfg.get('mem') or '160GB'
    route = cfg.get('route') or '#p opt freq B3LYP/6-31G(d)'
    title = cfg.get('title') or name
    chk = cfg.get('chk')
    if not chk:
        suffix = cfg.get('chk_suffix', '_opt')
        chk = '%s%s.chk' % (name, suffix)
    trailing = int(cfg.get('trailing_blank_lines', 2))

    lines = []
    lines.append('%%nprocshared=%d' % nproc)
    lines.append('%%mem=%s' % mem)
    lines.append('%%chk=%s' % chk)
    lines.append(route)
    lines.append('')
    lines.append(title)
    lines.append('')
    lines.append('%d %d' % (int(charge), int(multiplicity)))
    for sym, x, y, z in atoms:
        lines.append(format_atom(sym, x, y, z))
    # 坐标块之后必须留空行；用户要求留两个
    body = '\n'.join(lines) + '\n' * (1 + trailing)
    return body


def build_readchk_gjf(name, charge, multiplicity, cfg, suffix='_td',
                      route=None, title=None, nproc=None, mem=None):
    """读已有基态 chk 的作业（TD 单点 / 单独 freq）：%oldchk 指向基态，自己的 chk 另起名。"""
    cfg = dict(cfg or {})
    base_chk = cfg.get('base_chk') or ('%s%s.chk' % (name, cfg.get('chk_suffix', '_opt')))
    own_chk = cfg.get('own_chk') or ('%s%s.chk' % (name, suffix))
    nproc = int(nproc or cfg.get('td_nproc') or cfg.get('nproc') or 32)
    mem = mem or cfg.get('td_mem') or cfg.get('mem') or '160GB'
    trailing = int(cfg.get('trailing_blank_lines', 2))
    lines = [
        '%%oldchk=%s' % base_chk,
        '%%chk=%s' % own_chk,
        '%%nprocshared=%d' % nproc,
        '%%mem=%s' % mem,
        route or '',
        '',
        title or '',
        '',
        '%d %d' % (int(charge), int(multiplicity)),
    ]
    return NL.join(lines) + NL * (1 + trailing)


def build_td_gjf(name, charge, multiplicity, cfg, opt_chk=None):
    """TD-DFT 单点输入（用户 2026-10-21 给的模板）：

        %oldchk=mol_opt.chk
        %chk=mol_td.chk
        %nprocshared=8
        %mem=16GB
        #p PBE1PBE/def2TZVP TD(NStates=10, Singlet) Geom=Check Guess=Read

        TD-DFT UV-Vis calculation at PBE0/def2-TZVP level

        0 1
    （不写坐标：Geom=Check 从 opt 的 chk 里读结构和电荷）
    """
    from . import methods
    cfg = dict(cfg or {})
    func = methods.get_functional(cfg.get('functional'))
    basis = methods.get_basis(cfg.get('basis'))
    nstates = int(cfg.get('td_states') or 10)
    route = cfg.get('route') or ('#p %s/%s TD(NStates=%d, Singlet) Geom=Check Guess=Read'
                                 % (func['key'], basis['key'], nstates))
    title = cfg.get('title') or ('TD-DFT UV-Vis calculation at %s level'
                                 % methods.method_summary(cfg))
    cfg = dict(cfg)
    if opt_chk:
        cfg['base_chk'] = opt_chk
    cfg['own_chk'] = cfg.get('td_chk') or ('%s_td.chk' % name)
    return build_readchk_gjf(name, charge, multiplicity, cfg, suffix='_td',
                             route=route, title=title,
                             nproc=cfg.get('td_nproc') or cfg.get('nproc') or 32,
                             mem=cfg.get('td_mem') or cfg.get('mem') or '160GB')


def build_vibronic_gs_gjf(name, charge, multiplicity, cfg):
    """振动分辨第一步：基态 opt + freq=(saveNM)，把简正模存进 chk。"""
    cfg = dict(cfg or {})
    route = cfg.get('route') or ('#p opt freq=(SaveNormalModes) %s/%s' % (cfg.get('func_key', 'PBE1PBE'),
                                                                          cfg.get('basis_key', 'def2TZVP')))
    title = cfg.get('title') or ('Ground state opt+freq (saveNM) for vibronic spectrum')
    chk = '%s_gs.chk' % name
    lines = ['%%nprocshared=%d' % int(cfg.get('nproc') or 32),
             '%%mem=%s' % (cfg.get('mem') or '160GB'),
             '%%chk=%s' % chk,
             route, '', title, '',
             '%d %d' % (int(charge), int(multiplicity))]
    for sym, x, y, z in (cfg.get('atoms') or []):
        lines.append(COORD_FMT % (sym, x, y, z))
    return NL.join(lines) + NL * (1 + int(cfg.get('trailing_blank_lines', 2)))


def build_vibronic_fc_gjf(name, charge, multiplicity, cfg, gs_chk=None):
    """振动分辨第二步：读基态 chk，做 FC/HT 振动分辨激发态计算。"""
    cfg = dict(cfg or {})
    from . import methods
    func = methods.get_functional(cfg.get('functional'))
    basis = methods.get_basis(cfg.get('basis'))
    nstates = int(cfg.get('td_states') or 10)
    route = ('#p Freq=(ReadFC,FC,HT) TD=(NStates=%d, Singlet, Read) %s/%s'
             ' Geom=Check Guess=Read' % (nstates, func['key'], basis['key']))
    title = cfg.get('title') or ('Vibronically resolved UV-Vis spectrum at %s level'
                                 % methods.method_summary(cfg))
    gs_chk = gs_chk or ('%s_gs.chk' % name)
    lines = ['%%oldchk=%s' % gs_chk,
             '%%chk=%s_fc.chk' % name,
             '%%nprocshared=%d' % int(cfg.get('nproc') or 32),
             '%%mem=%s' % (cfg.get('mem') or '160GB'),
             route, '', title, '',
             '%d %d' % (int(charge), int(multiplicity))]
    return NL.join(lines) + NL * (1 + int(cfg.get('trailing_blank_lines', 2)))


def write_gjf(path, text, crlf=True):
    data = text.replace('\n', '\r\n') if crlf else text
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(data)
    return path


def read_gjf_atoms(path):
    """读一个 .gjf 的坐标块（给预览/校验用）。"""
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        lines = fh.read().replace('\r\n', '\n').split('\n')
    i = None
    for k, ln in enumerate(lines):
        if ln.strip().startswith('#') and k + 1 < len(lines):
            i = k
            break
    if i is None:
        return []
    # 跳过 route 之后的空行、标题、空行，找到电荷/多重度行
    j = i + 1
    while j < len(lines) and not lines[j].strip():
        j += 1
    j += 1  # 标题
    while j < len(lines) and not lines[j].strip():
        j += 1
    j += 1  # 电荷多重度
    atoms = []
    while j < len(lines):
        parts = lines[j].split()
        if len(parts) < 4:
            break
        try:
            atoms.append((parts[0], float(parts[1]), float(parts[2]), float(parts[3])))
        except ValueError:
            break
        j += 1
    return atoms


def find_gjf_files(folder):
    out = []
    for fn in sorted(os.listdir(folder)):
        if fn.lower().endswith('.gjf') or fn.lower().endswith('.com'):
            out.append(os.path.join(folder, fn))
    return out
