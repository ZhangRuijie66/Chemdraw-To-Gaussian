# -*- coding: utf-8 -*-
"""Chem3D（ChemScript）3D 生成 worker —— 必须用 Python 3.9 / 3.10 运行。

用法（由 gcalc/chem3d.py 用子进程调用，一般不手敲）：

    python310\\python.exe chem3d_worker.py <输入.cdxml> <输出.json> [ChemScript Lib 目录]

为什么单独一个进程：主程序跑在 Python 3.11（装了 RDKit），而 ChemScript 只提供
`_ChemScriptForPy39.pyd` / `_ChemScriptForPy310.pyd`，3.11 里 import 会直接失败。
所以主程序把这一步甩给 3.9/3.10 的子进程，结果用 JSON 传回来。

输出 JSON：

    {"ok": true,
     "atoms": [[symbol, x, y, z], ...],       # 已加氢、已 MM2 最小化
     "bonds": [[i, j, order], ...],            # 下标对应 atoms
     "charge": 1, "formula": "C21H21N2S2+",
     "mm2_energy": 36.68, "mm2_rounds": 2,
     "n_atoms_2d": 25, "n_atoms_3d": 46, ...}

踩过的坑（详见 _tmp_recon/chem3d/报告.md）：

1. **ReadFile/WriteFile 不认非 ASCII 路径**：中文路径下 `ReadFile` 静默返回 None、
   `len(sd.Atoms) == 0`，**不抛异常**。所以输入先复制到 ASCII 暂存目录再读。
2. API 形状和文档有出入：`Atom.Element` 直接是元素符号字符串；坐标用
   `Atom.GetCartesian()`（Point，小写 `.x/.y/.z`）；键级在 `Bond.Order.BondCode`；
   `Bond.Atom1/Atom2` 要拿 `.ID` 映射回下标。
3. `Mm2OptimizeGeometry` 返回 `ChemScript.Dictionary_String_Double`（`dict()` 能转，
   `isinstance(res, dict)` 是 False），能量从里面的 `Total` 取。
4. **单次 MM2 不一定收敛**：要循环到「坐标位移 < 0.005 Å 且能量变化 < 0.01 kcal/mol」，
   只看坐标不动会早停（第一轮有时报 0.0 位移但能量还差 1 kcal/mol）。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import traceback

# 与 gcalc/gjf.py 的坐标格式一致（这里只用于日志，不写 .gjf）
DEFAULT_LIB = r'C:\Program Files\PerkinElmerInformatics\ChemOffice\ChemScript\Lib'

# MM2 收敛判据（报告第 5 节）
MM2_RMS_GRADIENT = 0.005
MM2_MAX_ITERATIONS = 5000
DISP_TOL = 0.005      # Å
ENERGY_TOL = 0.01     # kcal/mol
MAX_ROUNDS = 10


def _quiet_console():
    """子进程输出可能被父进程按 UTF-8 解码，先把控制台编码的错误吞掉。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except (AttributeError, ValueError, OSError):
            pass


def _ascii_dir(path):
    try:
        path.encode('ascii')
        return True
    except UnicodeEncodeError:
        return False


def work_dir():
    """找一个纯 ASCII 的暂存目录（ChemScript 只认 ASCII 路径）。"""
    cands = []
    env = os.environ.get('CHEM3D_WORK')
    if env:
        cands.append(env)
    cands.append(os.path.join(os.environ.get('SystemDrive', 'C:') + os.sep,
                              'Temp', 'chem3dwork'))
    tmp = tempfile.gettempdir()
    if _ascii_dir(tmp):
        cands.append(os.path.join(tmp, 'chem3dwork'))
    cands.append(os.path.join('C:' + os.sep, 'Temp', 'chem3dwork'))
    last = None
    for d in cands:
        if not _ascii_dir(d):
            continue
        try:
            os.makedirs(d, exist_ok=True)
            fd, probe = tempfile.mkstemp(prefix='.write_test_', dir=d)
            os.close(fd)
            os.remove(probe)
            return d
        except OSError as exc:  # 权限/盘符不存在，换下一个
            last = exc
    raise RuntimeError('找不到可写的 ASCII 暂存目录（可设环境变量 CHEM3D_WORK）：%s'
                       % last)


def import_chemscript(lib):
    """把 ChemScript 的 Lib 及其依赖 DLL 目录加进去，返回模块。"""
    lib = os.path.abspath(lib)
    root = os.path.dirname(os.path.dirname(lib))  # ...\ChemOffice
    dll_dirs = [lib, root,
                os.path.join(root, 'Chem3D'),
                os.path.join(root, 'Common'),
                os.path.join(root, 'ChemDraw')]
    if hasattr(os, 'add_dll_directory'):
        for d in dll_dirs:
            if os.path.isdir(d):
                try:
                    os.add_dll_directory(d)
                except OSError:
                    pass
    # 坑：本机 PYTHONPATH 里可能同时有 32 位的
    # `C:\Program Files (x86)\...\ChemScript\Lib` 和 64 位的
    # `C:\Program Files\...\ChemScript\Lib`。如果只 insert(0) 而不把别的
    # ChemScript\Lib 摘掉，import 会撞上先出现的那一个；32 位 .pyd 被 64 位
    # Python 加载就报「DLL load failed ... 不是有效的 Win32 应用程序」。
    wanted = os.path.normcase(os.path.normpath(lib))
    tail = os.path.normcase(os.path.join('ChemScript', 'Lib'))
    sys.path[:] = [p for p in sys.path
                   if not (p and os.path.normcase(os.path.normpath(p)).endswith(tail)
                           and os.path.normcase(os.path.normpath(p)) != wanted)]
    sys.path.insert(0, lib)
    try:
        import ChemScript  # noqa: E402
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            'import ChemScript 失败（%s）。检查：1) 这个解释器是不是 3.9/3.10；'
            '2) ChemScript 路径对不对（当前 %s）；3) ChemOffice 是否装在本机；'
            '4) 有没有撞上 32 位的 ChemScript（Program Files (x86)）。'
            % (exc, lib))
    return ChemScript


def stage_input(path):
    """复制到 ASCII 暂存目录，返回暂存文件路径（ChemScript 只认 ASCII 路径）。"""
    d = work_dir()
    ext = os.path.splitext(path)[1] or '.cdxml'
    # 文件名也要纯 ASCII；用 mkstemp 保证并发调用（网页是多线程）不会互相覆盖
    fd, dst = tempfile.mkstemp(prefix='in_', suffix=ext, dir=d)
    os.close(fd)
    shutil.copyfile(path, dst)
    return dst


def atoms_of(sd):
    out = []
    for atom in sd.Atoms:
        p = atom.GetCartesian()
        out.append([str(atom.Element), float(p.x), float(p.y), float(p.z)])
    return out


def bonds_of(sd):
    index = {a.ID: i for i, a in enumerate(sd.Atoms)}
    out = []
    for b in sd.Bonds:
        code = getattr(b.Order, 'BondCode', b.Order)
        try:
            code = float(code)
        except (TypeError, ValueError):
            code = 1.0
        i = index.get(b.Atom1.ID, -1)
        j = index.get(b.Atom2.ID, -1)
        if i < 0 or j < 0:
            continue
        out.append([i, j, code])
    return out


def mm2_energy(sd):
    try:
        return float(sd.Mm2Energy())
    except Exception:  # noqa: BLE001
        return None


def mm2_optimize(sd):
    """循环 Mm2OptimizeGeometry 到「位移 + 能量」都不再变，返回统计信息。"""
    info = {'mm2_before': mm2_energy(sd)}
    prev_atoms = atoms_of(sd)
    prev_energy = info['mm2_before']
    rounds, terms, disp = 0, {}, float('inf')
    for rounds in range(1, MAX_ROUNDS + 1):
        res = sd.Mm2OptimizeGeometry(rmsGradient=MM2_RMS_GRADIENT,
                                     maxIterations=MM2_MAX_ITERATIONS)
        try:
            terms = {str(k): float(v) for k, v in dict(res).items()}
        except (TypeError, ValueError):
            terms = {}
        cur_atoms = atoms_of(sd)
        disp = max(max(abs(a[i] - b[i]) for i in (1, 2, 3))
                   for a, b in zip(prev_atoms, cur_atoms))
        prev_atoms = cur_atoms
        energy = terms.get('Total', mm2_energy(sd))
        if (disp < DISP_TOL and prev_energy is not None
                and energy is not None and abs(energy - prev_energy) < ENERGY_TOL):
            break
        prev_energy = energy
    info.update(mm2_rounds=rounds, mm2_last_disp=round(disp, 6),
                mm2_terms=terms, mm2_energy=terms.get('Total', mm2_energy(sd)))
    return info


def run(src, lib):
    t0 = time.time()
    ChemScript = import_chemscript(lib)
    staged = stage_input(src)
    try:
        sd = ChemScript.StructureData()
        mime = sd.ReadFile(staged)
        if not mime or len(sd.Atoms) == 0:
            raise RuntimeError(
                'ChemScript 读取失败：%s（mime=%r，原子数=%d）。'
                '常见原因：文件不是有效的 .cdxml，或路径不是纯 ASCII（已尝试暂存）。'
                % (src, mime, len(sd.Atoms)))
        info = {'input': os.path.abspath(src), 'mime': str(mime),
                'formula_2d': str(sd.Formula()), 'charge': int(sd.TotalCharge),
                'n_atoms_2d': len(sd.Atoms)}
        t_conv = time.time()
        if not sd.ConvertTo3DStructure(addHydrogen=True):
            raise RuntimeError('ConvertTo3DStructure 失败（2D → 3D）：%s' % src)
        info['n_atoms_3d'] = len(sd.Atoms)
        info['t_convert_s'] = round(time.time() - t_conv, 3)
        if info['n_atoms_3d'] == 0:
            raise RuntimeError('2D → 3D 之后没有原子：%s' % src)
        t_mm2 = time.time()
        info.update(mm2_optimize(sd))
        info['t_mm2_s'] = round(time.time() - t_mm2, 3)
        info.update(ok=True, atoms=atoms_of(sd), bonds=bonds_of(sd),
                    formula=str(sd.Formula()), charge=int(sd.TotalCharge),
                    source='ChemScript / Chem3D ConvertTo3DStructure + MM2',
                    t_total_s=round(time.time() - t0, 3))
        return info
    finally:
        try:
            os.remove(staged)
        except OSError:
            pass


def main(argv):
    _quiet_console()
    if len(argv) < 2:
        sys.stderr.write('用法：chem3d_worker.py <输入.cdxml> <输出.json> [ChemScript Lib]\n')
        return 2
    src = os.path.abspath(argv[0])
    out = os.path.abspath(argv[1])
    lib = argv[2] if len(argv) > 2 and argv[2].strip() else (
        os.environ.get('CHEMSCRIPT_LIB') or DEFAULT_LIB)
    if not os.path.isfile(src):
        sys.stderr.write('输入文件不存在：%s\n' % src)
        return 2
    try:
        payload = run(src, lib)
        code = 0
    except Exception as exc:  # noqa: BLE001
        payload = {'ok': False, 'error': '%s: %s' % (type(exc).__name__, exc),
                   'traceback': traceback.format_exc(limit=8)}
        code = 1
        sys.stderr.write(payload['traceback'])
    try:
        parent = os.path.dirname(out)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(out, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
    except OSError as exc:
        sys.stderr.write('写结果 JSON 失败：%s\n' % exc)
        return 3
    if code == 0:
        sys.stdout.write('OK %s  atoms=%d  formula=%s  charge=%d  MM2=%.4f (%d 轮)\n'
                         % (os.path.basename(src), len(payload['atoms']),
                            payload['formula'], payload['charge'],
                            payload.get('mm2_energy') or float('nan'),
                            payload.get('mm2_rounds') or 0))
    return code


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
