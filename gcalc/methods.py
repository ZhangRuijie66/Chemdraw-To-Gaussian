# -*- coding: utf-8 -*-
"""高斯常见泛函 / 基组 / 任务类型的目录，以及 route 行（#p …）的拼装。

关键词写法按 Gaussian 16 手册（用户 2026-10-21 要求"查询常见泛函、基组、方法的写法"）：
  · 泛函直接写在 route 里：`#p opt freq B3LYP/6-31G(d)`
  · PBE0 在 Gaussian 里的关键词是 **PBE1PBE**（等价写法 PBE0 也认，但模板用 PBE1PBE）
  · 色散校正：`EmpiricalDispersion=GD3BJ`（D3 的 Becke–Johnson 阻尼）、`GD3`（零阻尼）
  · 积分格点：`Int=(UltraFine,NoXCTest)`；SCF 加速：`SCF=NoVarAcc`（G16 C.01+）
  · 隐式溶剂：`SCRF=(IEFPCM,Solvent=Ethanol)` / `SCRF=(SMD,Solvent=Ethanol)`
  · TD-DFT：`TD=(NStates=10,Singlets)`，常与 `geom=check guess=read` 配合读优化结构
"""
from __future__ import annotations

# ---------------------------------------------------------------- 泛函
FUNCTIONALS = [
    # key, 显示名, 说明, 是否自带色散
    ('B3LYP', 'B3LYP', '最常用的 B3 杂化泛函；基态几何、振动频率的默认选择', False),
    ('PBE1PBE', 'PBE0', 'PBE 杂化（25% HF 交换）；几何与激发能都比 B3LYP 略好', False),
    ('M062X', 'M06-2X', 'Meta 杂化，54% HF 交换，主族热化学与激发能，色散已含', True),
    ('wB97XD', 'ωB97X-D', '长程校正 + 自带色散；电荷转移激发、极化体系常用', True),
    ('CAM-B3LYP', 'CAM-B3LYP', '长程校正 B3LYP；CT 态、Rydberg 激发常用', False),
    ('B3PW91', 'B3PW91', 'B3 与 PW91 组合；与 B3LYP 相近，金属体系稍好', False),
    ('TPSSTPSS', 'TPSSh', 'Meta 杂化 TPSS；对过渡金属与弱相互作用较好', False),
    ('B3LYP5', 'B3LYP(5)', '含 5 个纯 DFT 交换的 B3LYP 老定义（复现老文献时用）', False),
    ('HF', 'HF', 'Hartree–Fock；只作参考，不含电子相关', False),
]

# ---------------------------------------------------------------- 基组
BASIS_SETS = [
    ('6-31G(d)', '6-31G(d)', 'Pople 双 ζ + 重原子 d 极化；性价比最高，几何优化常用', 'pople'),
    ('6-31+G(d,p)', '6-31+G(d,p)', '再加弥散与 H 极化；阴离子、弱相互作用', 'pople'),
    ('6-311G(d,p)', '6-311G(d,p)', '三 ζ Pople + 极化；比 6-31G(d) 更准', 'pople'),
    ('6-311+G(d,p)', '6-311+G(d,p)', '三 ζ + 弥散 + H 极化；阴离子/激发能', 'pople'),
    ('TZVP', 'TZVP', 'Ahlrichs 三 ζ（老写法，用户之前的 log 里就是它）', 'ahlrichs'),
    ('def2SVP', 'def2-SVP', 'Ahlrichs 双 ζ；主族元素平衡，重元素自带 ECP', 'ahlrichs'),
    ('def2TZVP', 'def2-TZVP', 'Ahlrichs 三 ζ + 极化；模板用的就是它', 'ahlrichs'),
    ('def2TZVPP', 'def2-TZVPP', '三 ζ + 双极化；更贵、更准', 'ahlrichs'),
    ('cc-pVDZ', 'cc-pVDZ', '相关一致双 ζ；与高精度方法配套', 'cc'),
    ('cc-pVTZ', 'cc-pVTZ', '相关一致三 ζ；计算量大', 'cc'),
    ('aug-cc-pVTZ', 'aug-cc-pVTZ', '增强相关一致三 ζ；激发态/Rydberg', 'cc'),
    ('LANL2DZ', 'LANL2DZ', 'Los Alamos 赝势；过渡金属常用（轻元素精度低）', 'ecp'),
    ('SDD', 'SDD', 'Stuttgart–Dresden 赝势；重元素几何优化', 'ecp'),
]

# ---------------------------------------------------------------- 任务类型
JOBS = [
    ('opt_freq', 'opt freq', '优化 + 频率（模板默认；确认是极小点并得到热力学量）'),
    ('opt', 'opt', '只优化几何'),
    ('freq', 'freq', '只算频率（几何用 geom=check 从 chk 读）'),
    ('td', 'TD-DFT 单点', '单点激发能（需先用 opt 优化）'),
    ('opt_td', 'opt + TD', '优化后在同一任务里算 TD（慢，适合小分子）'),
    ('vibronic', '振动分辨 (FC/HT)', '生成两个文件：基态 opt+freq(saveNM) + FC/HT 振动分辨 TD（很贵）'),
]

DISPERSIONS = [
    ('GD3BJ', 'GD3(BJ)', 'Becke–Johnson 阻尼；与 B3LYP/PBE0 搭配的常用选择'),
    ('GD3', 'D3(0)', '零阻尼；老文献/复现时用'),
    ('', '不加色散', '泛函本身已含色散（M06-2X、ωB97X-D）或只需 HF 时选'),
]

SOLVENTS = [
    ('', '气相'),
    ('Ethanol', '乙醇'),
    ('Methanol', '甲醇'),
    ('Water', '水'),
    ('Chloroform', '氯仿'),
    ('Dichloromethane', '二氯甲烷'),
    ('Acetonitrile', '乙腈'),
    ('DimethylSulfoxide', 'DMSO'),
    ('Toluene', '甲苯'),
]

SOLVATION_MODELS = [
    ('IEFPCM', 'IEFPCM（默认）'),
    ('SMD', 'SMD（更接近实验溶剂化自由能）'),
]


def get_functional(key):
    for k, name, desc, has_disp in FUNCTIONALS:
        if k.lower() == (key or '').lower():
            return dict(key=k, name=name, desc=desc, has_disp=has_disp)
    return dict(key='B3LYP', name='B3LYP', desc='', has_disp=False)


def get_basis(key):
    for k, name, desc, fam in BASIS_SETS:
        if k.lower() == (key or '').lower():
            return dict(key=k, name=name, desc=desc, family=fam)
    return dict(key='def2TZVP', name='def2-TZVP', desc='', family='ahlrichs')


def build_route(cfg):
    """按配置拼 route 行（不含开头的 '#p'）。"""
    job = (cfg.get('job') or 'opt_freq')
    func = get_functional(cfg.get('functional'))
    basis = get_basis(cfg.get('basis'))

    parts = []
    if job == 'opt_freq':
        parts += ['opt', 'freq']
    elif job == 'opt_td':
        parts += ['opt', 'freq']
    elif job == 'freq':
        parts += ['freq', 'geom=check']
    elif job == 'td':
        parts += ['TD(NStates=%d, Singlet)' % int(cfg.get('td_states') or 10),
                  'Geom=Check', 'Guess=Read']
    elif job == 'vibronic':
        # FC/HT 振动分辨：先有基态 freq=(saveNM)，这里读它并算激发态 Hessian
        parts += ['Freq=(ReadFC,FC,HT)',
                  'TD=(NStates=%d, Singlet, Read)' % int(cfg.get('td_states') or 10),
                  'Geom=Check', 'Guess=Read']
    else:
        parts.append(job)

    parts.append('%s/%s' % (func['key'], basis['key']))

    disp = cfg.get('dispersion', 'GD3BJ')
    if disp and not func['has_disp'] and cfg.get('use_dispersion', True):
        parts.append('EmpiricalDispersion=%s' % disp)

    if cfg.get('use_ultrafine', True):
        parts.append('Int=(UltraFine,NoXCTest)')
    if cfg.get('use_scfacc', True):
        parts.append('SCF=NoVarAcc')

    solvent = cfg.get('solvent') or ''
    if solvent:
        model = cfg.get('solvation_model') or 'IEFPCM'
        parts.append('SCRF=(%s,Solvent=%s)' % (model, solvent))

    if job == 'opt_td':
        parts.append('TD=(NStates=%d,Singlets)' % int(cfg.get('td_states') or 10))

    return ' '.join(parts)


def route_line(cfg):
    return '#p ' + build_route(cfg)


def method_summary(cfg):
    func = get_functional(cfg.get('functional'))
    basis = get_basis(cfg.get('basis'))
    return '%s/%s' % (func['name'], basis['name'])
