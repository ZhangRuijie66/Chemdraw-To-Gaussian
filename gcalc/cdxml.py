# -*- coding: utf-8 -*-
"""ChemDraw 文件解析：.cdxml 直接读，.cdx 先用 ChemDraw 转成 molfile。

CDXML 是 ChemDraw 的 XML 格式：<fragment> 里 <n> 是原子（p 给出 2D 坐标、
Element 给出原子序数、Charge 给出形式电荷），<b> 是键（B/E 是两端原子 id，
Order 是键级，缺省为 1）。隐式氢不在文件里，由 RDKit 按价态补齐。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from rdkit import Chem

PT = Chem.GetPeriodicTable()

BOND_TYPES = {
    1.0: Chem.BondType.SINGLE,
    1.5: Chem.BondType.AROMATIC,
    2.0: Chem.BondType.DOUBLE,
    3.0: Chem.BondType.TRIPLE,
}


class ChemDrawError(RuntimeError):
    pass


def _element(sym_or_z):
    if sym_or_z is None:
        return 'C'
    s = str(sym_or_z).strip()
    if s.isdigit():
        return PT.GetElementSymbol(int(s))
    return s.capitalize()


def parse_cdxml(path):
    """解析 .cdxml，返回 RDKit Mol（带 2D 坐标，隐式氢未加）。"""
    root = ET.parse(path).getroot()
    frags = root.findall('.//fragment')
    if not frags:
        raise ChemDrawError('%s 里没有找到 fragment（不是有效的 CDXML？）' % os.path.basename(path))

    # 只有一个 fragment 时直接用它；多个 fragment（如阴阳离子分开画）时
    # 取原子数最多的那个，并在返回信息里提示。
    n_frags = len(frags)
    chk = ''
    if n_frags > 1:
        chk = ('CDXML 里有 %d 个片段，只取最大的那个分子（其余忽略）' % n_frags)
    frags = sorted(frags, key=lambda f: len(f.findall('n')), reverse=True)
    frag = frags[0]
    nodes = frag.findall('n')
    bonds = frag.findall('b')

    rw = Chem.RWMol()
    idx = {}
    coords = []
    for n in nodes:
        atom = Chem.Atom(_element(n.get('Element')))
        q = n.get('Charge')
        if q:
            atom.SetFormalCharge(int(q))
        # 显式氢（ChemDraw 里画出来的 H）
        hcount = n.get('NumHydrogens')
        if hcount:
            atom.SetNoImplicit(True)
            atom.SetNumExplicitHs(int(hcount))
        idx[n.get('id')] = rw.AddAtom(atom)
        px = n.get('p', '0 0').split()
        coords.append((float(px[0]), float(px[1])))

    aromatic = False
    for b in bonds:
        order = float(b.get('Order', '1') or 1)
        bt = BOND_TYPES.get(order, Chem.BondType.SINGLE)
        if bt == Chem.BondType.AROMATIC:
            aromatic = True
        rw.AddBond(idx[b.get('B')], idx[b.get('E')], bt)

    mol = rw.GetMol()
    conf = Chem.Conformer(mol.GetNumAtoms())
    for i, (x, y) in enumerate(coords):
        conf.SetAtomPosition(i, (x * 0.05, -y * 0.05, 0.0))
    mol.AddConformer(conf)

    if aromatic:
        for b in mol.GetBonds():
            if b.GetBondType() == Chem.BondType.AROMATIC:
                b.GetBeginAtom().SetIsAromatic(True)
                b.GetEndAtom().SetIsAromatic(True)
    try:
        Chem.SanitizeMol(mol)
    except Exception as exc:  # noqa: BLE001
        raise ChemDrawError('结构价态检查失败（%s），请检查 ChemDraw 里的电荷/键级' % exc)

    # 关键：从 ChemDraw 的 2D 坐标判定双键的 E/Z（顺反）。
    # 不做这一步，ETKDG 会随机选顺反，长链分子（如 β-胡萝卜素）会被建成
    # 一堆顺式双键，优化后平面性很差、吸收峰也偏蓝。
    try:
        Chem.DetectBondStereoChemistry(mol, mol.GetConformer())
        Chem.AssignStereochemistry(mol, cleanIt=False, force=True)
    except Exception:  # noqa: BLE001
        pass
    if chk:
        mol.SetProp('_fragment_note', chk)
    return mol


def _powershell_exe():
    """找一个可用的 PowerShell：优先 pwsh 7，退回系统自带的 Windows PowerShell。"""
    for name in ('pwsh', 'powershell'):
        p = shutil.which(name)
        if p:
            return p
    for cand in (r'C:\Program Files\PowerShell\pwsh.exe',
                 r'C:\Windows\System32\WindowsPowerShell1.0\powershell.exe'):
        if os.path.exists(cand):
            return cand
    return 'powershell'


def _powershell_convert_cdx(cdx_path, mol_path):
    """用 ChemDraw 的 COM 接口把 .cdx 另存为 .mol（必须用纯 ASCII 临时路径）。"""
    ps = (
        "$ErrorActionPreference='Stop';"
        "try{"
        "$app=New-Object -ComObject 'ChemDraw.Application';"
        "$app.Visible=$false;"
        "$doc=$app.Documents.Open('%s');"
        "$doc.SaveAs('%s');"
        "$doc.Close();$app.Quit();"
        "Write-Output 'OK'"
        "}catch{Write-Output ('ERR '+$_.Exception.Message);try{$app.Quit()}catch{}}"
        % (cdx_path.replace("'", "''"), mol_path.replace("'", "''"))
    )
    exe = _powershell_exe()
    try:
        out = subprocess.run([exe, '-NoProfile', '-NonInteractive', '-Command', ps],
                             capture_output=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ChemDrawError('调用 ChemDraw 失败：%s' % exc)
    txt = (out.stdout or b'').decode('utf-8', 'replace')
    if 'OK' not in txt or not os.path.exists(mol_path):
        raise ChemDrawError('ChemDraw 转换失败：%s' % txt.strip()[:200])


def load_molecule(path):
    """读 .cdxml / .cdx / .mol，返回 (RDKit Mol, 提示信息列表)。"""
    ext = os.path.splitext(path)[1].lower()
    notes = []
    if ext == '.cdxml':
        mol = parse_cdxml(path)
        if mol.HasProp('_fragment_note'):
            notes.append(mol.GetProp('_fragment_note'))
        return mol, notes
    if ext == '.cdx':
        tmp = tempfile.mkdtemp(prefix='gcalc_')
        try:
            src = os.path.join(tmp, 'in.cdx')
            shutil.copyfile(path, src)
            dst = os.path.join(tmp, 'out.mol')
            _powershell_convert_cdx(src, dst)
            mol = Chem.MolFromMolFile(dst, removeHs=False, sanitize=True)
            if mol is None:
                raise ChemDrawError('ChemDraw 导出的 molfile 无法解析')
            notes.append('已用 ChemDraw 把 .cdx 转成 molfile')
            return mol, notes
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if ext in ('.mol', '.sdf'):
        mol = Chem.MolFromMolFile(path, removeHs=False, sanitize=True)
        if mol is None:
            raise ChemDrawError('molfile 解析失败')
        return mol, notes
    raise ChemDrawError('不支持的文件类型：%s（支持 .cdxml / .cdx / .mol / .sdf）' % ext)


def list_chemdraw_files(folder):
    exts = ('.cdxml', '.cdx', '.mol', '.sdf')
    out = []
    for fn in sorted(os.listdir(folder)):
        if fn.lower().endswith(exts) and not fn.startswith('~$'):
            out.append(os.path.join(folder, fn))
    return out


def molecule_info(mol):
    """分子基本信息：名称由调用方填，这里算式量/电荷/原子数。"""
    from rdkit.Chem import Descriptors, rdMolDescriptors
    return dict(
        formula=rdMolDescriptors.CalcMolFormula(mol),
        charge=Chem.GetFormalCharge(mol),
        heavy_atoms=mol.GetNumAtoms(),
        mol_wt=round(Descriptors.MolWt(mol), 2),
    )
