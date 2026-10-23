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


def _force_trans_double_bonds(mol):
    """把所有非环 C=C 强制成 E（反式）。

    共轭长链（花青、类胡萝卜素）实验上都是全反式伸展构象；ChemDraw 的手绘
    2D 图常有画歪的顺式键，照抄会得到弯折的起始结构。默认按反式生成。
    """
    rings = mol.GetRingInfo()
    for b in mol.GetBonds():
        if b.GetBondType() != Chem.BondType.DOUBLE:
            continue
        if rings.NumBondRings(b.GetIdx()):
            continue
        a1, a2 = b.GetBeginAtom(), b.GetEndAtom()
        if a1.GetSymbol() != 'C' or a2.GetSymbol() != 'C':
            continue
        # 取代基可能不止一个（例如双键一端是环原子，环上有两个邻居），
        # 取第一个邻居作参考即可；环内双键上面已经跳过了。
        n1 = [n.GetIdx() for n in a1.GetNeighbors() if n.GetIdx() != a2.GetIdx()]
        n2 = [n.GetIdx() for n in a2.GetNeighbors() if n.GetIdx() != a1.GetIdx()]
        if not n1 or not n2:
            continue
        n1, n2 = n1[:1], n2[:1]
        # STEREOE 需要同时指明两个参考取代基，否则 ETKDG 看不到这个约束
        b.SetStereoAtoms(n1[0], n2[0])
        b.SetStereo(Chem.BondStereo.STEREOE)
    return mol


def embed_3d(mol, n_conformers=1, force_field='MMFF94', seed=0xf00d, max_iters=2000,
             force_trans=None):
    """mol（带 2D 坐标）→ 加氢、嵌入、力场优化后返回 3D mol。

    force_trans=True（默认）把非环 C=C 全部按反式处理：共轭长链（花青、
    类胡萝卜素）实验上都是全反式伸展构象，照抄手绘的顺式键会得到弯折结构。
    """
    if force_trans is None:
        force_trans = True
    if force_trans:
        _force_trans_double_bonds(mol)
    molh = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = int(seed)
    params.numThreads = 0
    params.useSmallRingTorsions = True
    n = max(1, int(n_conformers))
    cids = list(AllChem.EmbedMultipleConfs(molh, numConfs=n, params=params))
    if not cids:
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
