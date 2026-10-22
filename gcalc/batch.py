# -*- coding: utf-8 -*-
"""批量流程：扫描 ChemDraw 文件 → 生成 3D → 写 .gjf。"""
from __future__ import annotations

import os

from . import cdxml, embed, gjf, methods

DEFAULT_CONFIG = dict(
    input_dir='',
    out_dir='',
    job='opt_freq',
    functional='PBE1PBE',
    basis='def2TZVP',
    dispersion='GD3BJ',
    use_dispersion=True,
    solvent='',
    solvation_model='IEFPCM',
    nproc=32,
    mem='160GB',
    td_states=10,
    n_conformers=1,
    force_field='MMFF94',
    trailing_blank_lines=2,
    chk_suffix='_opt',
    title_from='stem',
    two_step=False,
    crlf=True,
    # ---- 超算提交（Gaussian 作业）
    cluster='wm1',
    partition='C032M0128G',
    qos='low',
    nodes=1,
    ntasks=32,
    walltime='2-00:00:00',
    remote_dir='~/g16jobs',
    g16root='$HOME',
    scr_dir='$HOME/tmp',
    make_zip=True,
    hpc_host='',
    hpc_port=22,
    hpc_user='',
    sbatch_out='job.%j.out',
    include_env=False,
    job_tag='',
)

PERSIST_KEYS = ('input_dir', 'out_dir', 'job', 'functional', 'basis', 'dispersion',
                'use_dispersion', 'solvent', 'solvation_model', 'nproc', 'mem',
                'td_states', 'n_conformers', 'force_field', 'trailing_blank_lines',
                'chk_suffix', 'title_from', 'two_step', 'crlf',
                'cluster', 'partition', 'qos', 'nodes', 'ntasks', 'walltime',
                'remote_dir', 'g16root', 'scr_dir', 'make_zip',
                'hpc_host', 'hpc_port', 'hpc_user',
                'sbatch_out', 'include_env', 'job_tag', 'td_nproc', 'td_mem')


def default_config():
    return dict(DEFAULT_CONFIG)


def out_dir_for(cfg, fallback=None):
    d = (cfg.get('out_dir') or '').strip()
    if d:
        return d
    base = fallback or cfg.get('input_dir') or os.getcwd()
    # 默认写到输入目录下的 gjf 子文件夹，避免覆盖 Chem3D 直接导出的同名文件
    return os.path.join(base, 'gjf')


def scan(folder):
    """列出目录里的 ChemDraw 文件及其分子信息。"""
    items = []
    for path in cdxml.list_chemdraw_files(folder):
        name = os.path.splitext(os.path.basename(path))[0]
        item = dict(name=name, path=path, ext=os.path.splitext(path)[1].lower(),
                    ok=True, error='', formula='', charge=0, heavy_atoms=0, mol_wt=0.0)
        try:
            mol, notes = cdxml.load_molecule(path)
            item.update(cdxml.molecule_info(mol))
            item['notes'] = notes
        except Exception as exc:  # noqa: BLE001
            item['ok'] = False
            item['error'] = str(exc)
        items.append(item)
    return items


def _title(cfg, name):
    mode = cfg.get('title_from') or 'stem'
    if mode == 'stem':
        return name
    if mode == 'functional':
        return '%s %s' % (name, methods.method_summary(cfg))
    return name


def make_one(path, cfg, write=True):
    """单个文件 → (gjf 文本, 结果信息)。write=False 时只生成不落盘。"""
    name = os.path.splitext(os.path.basename(path))[0]
    mol, notes = cdxml.load_molecule(path)
    info = cdxml.molecule_info(mol)
    mol3d, ff = embed.embed_3d(mol,
                               n_conformers=int(cfg.get('n_conformers') or 1),
                               force_field=cfg.get('force_field') or 'MMFF94')
    atoms = embed.atoms_with_symbols(mol3d)

    # 振动分辨（FC/HT）要两个文件：基态 opt+freq(saveNM) + 读 chk 的 FC 计算
    if (cfg.get('job') or '') == 'vibronic':
        cfg2 = dict(cfg)
        cfg2['atoms'] = atoms
        cfg2['func_key'] = methods.get_functional(cfg.get('functional'))['key']
        cfg2['basis_key'] = methods.get_basis(cfg.get('basis'))['key']
        gs_text = gjf.build_vibronic_gs_gjf(name, info['charge'],
                                            int(cfg.get('multiplicity') or 1), cfg2)
        fc_text = gjf.build_vibronic_fc_gjf(name, info['charge'],
                                            int(cfg.get('multiplicity') or 1), cfg)
        result = dict(name=name, path=path, formula=info['formula'],
                      charge=info['charge'], atoms=len(atoms),
                      energy=ff.get('energy'), force_field=ff.get('force_field'),
                      route='FC/HT vibronic: see files', text=fc_text,
                      gs_text=gs_text, notes=notes, files=[])
        if write:
            out = out_dir_for(cfg, os.path.dirname(path))
            os.makedirs(out, exist_ok=True)
            f_gs = os.path.join(out, name + '_gs.gjf')
            f_fc = os.path.join(out, name + '_fc.gjf')
            gjf.write_gjf(f_gs, gs_text, crlf=bool(cfg.get('crlf', True)))
            gjf.write_gjf(f_fc, fc_text, crlf=bool(cfg.get('crlf', True)))
            result['files'] = [f_gs, f_fc]
        return result

    # 单独生成 TD / freq：读已有 chk，自己的 chk 另起名字，绝不动基态 chk
    job = (cfg.get('job') or '').lower()
    if job in ('td', 'freq'):
        mult = int(cfg.get('multiplicity') or 1)
        if job == 'td':
            text = gjf.build_td_gjf(name, info['charge'], mult, cfg,
                                    opt_chk='%s%s.chk' % (name, cfg.get('chk_suffix', '_opt')))
            suffix = '_td'
            route = text.splitlines()[4]
        else:
            route = methods.route_line(cfg)
            text = gjf.build_readchk_gjf(
                name, info['charge'], mult, cfg, suffix='_freq', route=route,
                title='Frequency calculation (geometry from %s%s.chk) at %s level'
                      % (name, cfg.get('chk_suffix', '_opt'), methods.method_summary(cfg)),
                nproc=cfg.get('nproc'), mem=cfg.get('mem'))
            suffix = '_freq'
        result = dict(name=name, path=path, formula=info['formula'],
                      charge=info['charge'], atoms=len(atoms),
                      energy=ff.get('energy'), force_field=ff.get('force_field'),
                      route=route, text=text, notes=notes, files=[])
        if write:
            out = out_dir_for(cfg, os.path.dirname(path))
            os.makedirs(out, exist_ok=True)
            f = os.path.join(out, name + suffix + '.gjf')
            gjf.write_gjf(f, text, crlf=bool(cfg.get('crlf', True)))
            result['files'] = [f]
        return result

    route = methods.route_line(cfg)
    text = gjf.build_gjf(
        name, atoms, charge=info['charge'], multiplicity=int(cfg.get('multiplicity') or 1),
        cfg=dict(route=route, title=_title(cfg, name),
                 nproc=cfg.get('nproc'), mem=cfg.get('mem'),
                 chk_suffix=cfg.get('chk_suffix', '_opt'),
                 trailing_blank_lines=int(cfg.get('trailing_blank_lines', 2))))

    result = dict(name=name, path=path, formula=info['formula'],
                  charge=info['charge'], atoms=len(atoms),
                  energy=ff.get('energy'), force_field=ff.get('force_field'),
                  route=route, text=text, notes=notes,
                  files=[])

    if write:
        out = out_dir_for(cfg, os.path.dirname(path))
        os.makedirs(out, exist_ok=True)
        f1 = os.path.join(out, name + '.gjf')
        gjf.write_gjf(f1, text, crlf=bool(cfg.get('crlf', True)))
        result['files'].append(f1)
        if cfg.get('two_step'):
            td_text = gjf.build_td_gjf(
                name, info['charge'], int(cfg.get('multiplicity') or 1), cfg,
                opt_chk='%s%s.chk' % (name, cfg.get('chk_suffix', '_opt')))
            f2 = os.path.join(out, name + '_td.gjf')
            gjf.write_gjf(f2, td_text, crlf=bool(cfg.get('crlf', True)))
            result['files'].append(f2)
            result['td_text'] = td_text
    return result


def make_many(paths, cfg):
    out = []
    for path in paths:
        try:
            out.append(make_one(path, cfg, write=True))
        except Exception as exc:  # noqa: BLE001
            out.append(dict(name=os.path.splitext(os.path.basename(path))[0],
                            path=path, error=str(exc), files=[]))
    return out
