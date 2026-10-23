# -*- coding: utf-8 -*-
"""可选 3D 后端：Chem3D（ChemScript）+ MM2，通过 Python 3.10 子进程调用。

主程序自己跑在 Python 3.11（装了 RDKit），而 ChemScript 只有 3.9/3.10 的扩展模块，
3.11 里 import 必失败。所以这里不改主程序解释器，而是：

    gcalc/chem3d.py（3.11 主程序）
        └─ subprocess → gcalc/chem3d_worker.py（3.10 + ChemScript）
                            └─ .cdxml → ConvertTo3DStructure → 循环 MM2 → out.json

配置项：
- `chem3d_python`：Python 3.9/3.10 解释器的完整路径；留空时读环境变量 CHEM3D_PYTHON。
- `chemscript_lib`：ChemScript 的 Lib 目录，默认
  `C:\\Program Files\\PerkinElmerInformatics\\ChemOffice\\ChemScript\\Lib`。

失败时抛 `Chem3DError`，消息里直接写明该去设置里填什么。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORKER = os.path.join(HERE, 'chem3d_worker.py')
DEFAULT_CHEMSCRIPT_LIB = (
    r'C:\Program Files\PerkinElmerInformatics\ChemOffice\ChemScript\Lib')
DEFAULT_TIMEOUT = 600  # 96 原子的 B1 整套 MM2 只要几秒，留足余量

_BACKEND_HINT = (
    '3D 后端选成了 Chem3D，但主程序跑在 Python %d.%d，import 不了 ChemScript。'
    '请在本工具「计算设置 → Chem3D Python」里填 Python 3.9/3.10 解释器的完整路径'
    '（例如 ...\\python310\\python.exe），或设置环境变量 CHEM3D_PYTHON。'
    % sys.version_info[:2])


class Chem3DError(RuntimeError):
    """Chem3D 子进程不可用 / 转换失败。消息面向用户，可以直接显示在网页上。"""


def chem3d_python(cfg=None):
    """取 Python 3.9/3.10 解释器路径：配置项 > 环境变量 CHEM3D_PYTHON。"""
    cfg = cfg or {}
    exe = str(cfg.get('chem3d_python') or '').strip().strip('"')
    if not exe:
        exe = (os.environ.get('CHEM3D_PYTHON') or '').strip().strip('"')
    if not exe:
        raise Chem3DError('还没有设置 Chem3D 的 Python 解释器。' + _BACKEND_HINT)
    exe = os.path.expanduser(os.path.expandvars(exe))
    if not os.path.isfile(exe):
        raise Chem3DError(
            'Chem3D Python 解释器不存在：%s\n'
            '请在本工具「计算设置 → Chem3D Python」里重新填 Python 3.9/3.10 的 '
            'python.exe 完整路径（或设环境变量 CHEM3D_PYTHON）。' % exe)
    return exe


def chemscript_lib(cfg=None):
    cfg = cfg or {}
    lib = str(cfg.get('chemscript_lib') or '').strip().strip('"')
    if not lib:
        lib = (os.environ.get('CHEMSCRIPT_LIB') or '').strip().strip('"')
    return lib or DEFAULT_CHEMSCRIPT_LIB


def _creationflags():
    """本地网页服务里起子进程时不要弹黑框（没有控制台就不加）。"""
    if os.name != 'nt':
        return 0
    return getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def _tail(text, limit=1600):
    text = (text or '').strip()
    if len(text) > limit:
        return '…' + text[-limit:]
    return text


def convert(cdxml_path, cfg=None, timeout=DEFAULT_TIMEOUT):
    """cdxml → {atoms, bonds, charge, formula, mm2_energy, mm2_rounds, ...}。

    atoms 是 [[symbol, x, y, z], ...]（已加氢、已 MM2 最小化），
    bonds 是 [[i, j, order], ...]（下标对应 atoms）。
    """
    cfg = cfg or {}
    src = os.path.abspath(str(cdxml_path))
    if not os.path.isfile(src):
        raise Chem3DError('输入文件不存在：%s' % cdxml_path)
    if not os.path.isfile(WORKER):
        raise Chem3DError('找不到 Chem3D worker 脚本：%s' % WORKER)
    exe = chem3d_python(cfg)
    lib = chemscript_lib(cfg)

    fd, out_json = tempfile.mkstemp(prefix='gcalc_chem3d_', suffix='.json')
    os.close(fd)
    env = dict(os.environ)
    env['CHEMSCRIPT_LIB'] = lib
    env['PYTHONIOENCODING'] = 'utf-8'
    cmd = [exe, WORKER, src, out_json, lib]
    try:
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, encoding='utf-8',
                errors='replace', timeout=timeout, env=env,
                cwd=os.path.dirname(HERE) or None,
                creationflags=_creationflags())
        except subprocess.TimeoutExpired:
            raise Chem3DError(
                'Chem3D 子进程超时（%d 秒）：%s\n'
                '大分子（如 β-胡萝卜素）MM2 会慢一些，可稍后重试；'
                '反复超时的话改用 RDKit 后端。' % (timeout, os.path.basename(src)))
        except OSError as exc:
            raise Chem3DError(
                '启动 Chem3D 子进程失败（%s）：%s\n'
                '请确认「Chem3D Python」填的是 Python 3.9/3.10 的 python.exe，'
                '而不是 3.11/3.12 或 pythonw.exe。' % (exe, exc))
        payload = _read_payload(out_json)
        if proc.returncode != 0 or not payload.get('ok'):
            detail = (payload.get('error') or '').strip()
            stderr = _tail(proc.stderr)
            msg = detail or stderr or '(子进程没有给出错误信息)'
            raise Chem3DError(
                'Chem3D 转换失败（退出码 %s）：%s\n\n详细信息：%s\n\n'
                '常见原因：1) 这个 Python 不是 3.9/3.10；2) ChemScript 路径不对'
                '（当前 %s）；3) 本机没装 ChemOffice；4) 撞上了 32 位的 ChemScript'
                '（PYTHONPATH 里的 Program Files (x86)）。' % (
                    proc.returncode, os.path.basename(src),
                    msg + (('\n' + stderr) if detail and stderr else ''), lib))
    finally:
        try:
            os.remove(out_json)
        except OSError:
            pass

    atoms = payload.get('atoms') or []
    if not atoms:
        raise Chem3DError('Chem3D 返回的原子列表是空的：%s' % cdxml_path)
    for a in atoms:
        if len(a) < 4:
            raise Chem3DError('Chem3D 返回的原子格式不对：%r' % (a,))
    return payload


def _read_payload(path):
    """读 worker 写的 JSON；子进程崩在 import 阶段时这里可能读不到。"""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def info_summary(result):
    """给网页/结果表用的一行摘要。"""
    return dict(
        atoms=len(result.get('atoms') or []),
        formula=result.get('formula') or '',
        charge=result.get('charge'),
        mm2_energy=result.get('mm2_energy'),
        mm2_rounds=result.get('mm2_rounds'),
        force_field='MM2',
    )
