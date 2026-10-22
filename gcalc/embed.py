# -*- coding: utf-8 -*-
"""把 2D 结构变成 3D 坐标：RDKit ETKDG 嵌入 + MMFF94 优化。

这一步替代手工的 "ChemDraw → Chem3D → MM2 最小化"：
ETKDG 先用距离几何生成初始构象，MMFF94 再做力场优化，得到可以交给 Gaussian
做 opt 的合理起始结构。多构象时取 MMFF 能量最低的那个。
"""
from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import AllChem

FORCE_FIELDS = [('MMFF94', 'MMFF94', '有机分子通用，参数覆盖好（默认）'),
                ('UFF', 'UFF', '兜底力场，MMFF 缺参数时用')]


class EmbedError(RuntimeError):
    pass


def embed_3d(mol, n_conformers=1, force_field='MMFF94', seed=0xf00d, max_iters=2000):
    """mol（带 2D 坐标）→ 加氢、嵌入、力场优化后返回 3D mol。"""
    molh = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = int(seed)
    params.numThreads = 0
    params.useSmallRingTorsions = True
    n = max(1, int(n_conformers))
    cids = list(AllChem.EmbedMultipleConfs(molh, numConfs=n, params=params))
    if not cids:
        # 再试一次更宽松的参数（大环/带电体系偶尔会失败）
        params.useRandomCoords = True
        cids = list(AllChem.EmbedMultipleConfs(molh, numConfs=n, params=params))
    if not cids:
        raise EmbedError('3D 嵌入失败：RDKit 无法为这个结构生成构象')

    ff = (force_field or 'MMFF94').upper()
    use_mmff = ff == 'MMFF94' and AllChem.MMFFHasAllMoleculeParams(molh)
    if ff == 'MMFF94' and not use_mmff:
        ff = 'UFF'

    results = []
    for cid in cids:
        if use_mmff:
            AllChem.MMFFOptimizeMolecule(molh, confId=cid, maxIters=max_iters)
            props = AllChem.MMFFGetMoleculeProperties(molh)
            ffobj = AllChem.MMFFGetMoleculeForceField(molh, props, confId=cid)
        else:
            AllChem.UFFOptimizeMolecule(molh, confId=cid, maxIters=max_iters)
            ffobj = AllChem.UFFGetMoleculeForceField(molh, confId=cid)
        energy = ffobj.CalcEnergy() if ffobj else float('nan')
        results.append((energy, cid))

    results.sort(key=lambda x: (x[0] if x[0] == x[0] else 1e9))
    best_energy, best_cid = results[0]
    out = Chem.Mol(molh, confId=best_cid)
    return out, dict(force_field=ff, energy=best_energy, n_conformers=len(cids))


def atoms_with_symbols(mol):
    """返回 [(symbol, x, y, z), ...]，直接可写进 .gjf。"""
    conf = mol.GetConformer()
    out = []
    for i, atom in enumerate(mol.GetAtoms()):
        p = conf.GetAtomPosition(i)
        out.append((atom.GetSymbol(), p.x, p.y, p.z))
    return out


def center_of_mass_shift(atoms):
    """把几何平移到质心在原点（Gaussian 无所谓，但看起来整齐）。"""
    if not atoms:
        return atoms
    n = float(len(atoms))
    cx = sum(a[1] for a in atoms) / n
    cy = sum(a[2] for a in atoms) / n
    cz = sum(a[3] for a in atoms) / n
    return [(s, x - cx, y - cy, z - cz) for s, x, y, z in atoms]
