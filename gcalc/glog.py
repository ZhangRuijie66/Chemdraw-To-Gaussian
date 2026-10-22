# -*- coding: utf-8 -*-
"""解析 Gaussian 输出（.log / .out），提取报告和复核要用的关键结果。

只依赖标准库，按 Gaussian 16 的固定格式用正则抓：
  · 状态：Normal termination / Error termination via Lnk1e in lXXX.exe
  · 电荷、多重度、原子数、route 行（泛函/基组）
  · SCF 能量（最后一个 "SCF Done:"）
  · 几何优化：是否找到驻点（"Stationary point found" / "Optimization completed"）
  · 频率：最后的 "Frequencies --" 行，负值即虚频
  · TD-DFT：逐条 "Excited State   n:  Singlet-A   E eV  λ nm  f=…"
  · 热化学：ZPE、Sum of electronic and thermal Free Energies
"""
from __future__ import annotations

import os
import re

RX = {
    'route': re.compile(r'^\s+#[pP]?\s*(.+)$', re.M),
    'charge': re.compile(r'Charge\s*=\s*(-?\d+)\s+Multiplicity\s*=\s*(\d+)'),
    'natoms': re.compile(r'NAtoms=\s*(\d+)'),
    'scf': re.compile(r'SCF Done:\s+E\([^)]+\)\s*=\s*(-?\d+\.\d+)'),
    'stationary': re.compile(r'Stationary point found'),
    'opt_completed': re.compile(r'Optimization completed'),
    'normal': re.compile(r'Normal termination of Gaussian'),
    'error': re.compile(r'Error termination via Lnk1e in\s+(\S+)\s+at\s+(.+)'),
    'freq': re.compile(r'Frequencies --\s+(.+)'),
    'exc': re.compile(r'Excited State\s+(\d+):\s+(\S+)\s+(-?\d+\.\d+)\s+eV\s+'
                      r'(-?\d+\.\d+)\s+nm\s+f=(-?\d+\.\d+)'),
    'zpe': re.compile(r'Sum of electronic and zero-point Energies=\s*(-?\d+\.\d+)'),
    'e_thermal': re.compile(r'Sum of electronic and thermal Energies=\s*(-?\d+\.\d+)'),
    'enthalpy': re.compile(r'Sum of electronic and thermal Enthalpies=\s*(-?\d+\.\d+)'),
    'gibbs': re.compile(r'Sum of electronic and thermal Free Energies=\s*(-?\d+\.\d+)'),
    'imag': re.compile(r'NImag=\s*(\d+)'),
}


def parse_log(path):
    """返回一个 dict；解析失败的字段给 None / 空列表。"""
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        text = fh.read()

    out = dict(file=path, name=os.path.splitext(os.path.basename(path))[0],
               status='unknown', error_link='', error_at='',
               route='', charge=None, mult=None, natoms=None,
               energy=None, n_scf=0, converged=None, n_opt_steps=0,
               frequencies=[], n_imag=None, excitations=[],
               zpe=None, e_thermal=None, enthalpy=None, gibbs=None,
               dipole=None, size=len(text))

    m = RX['route'].search(text)
    if m:
        out['route'] = m.group(1).strip()
    m = RX['charge'].search(text)
    if m:
        out['charge'] = int(m.group(1))
        out['mult'] = int(m.group(2))
    m = RX['natoms'].search(text)
    if m:
        out['natoms'] = int(m.group(1))

    scf = RX['scf'].findall(text)
    out['n_scf'] = len(scf)
    if scf:
        out['energy'] = float(scf[-1])

    out['converged'] = bool(RX['stationary'].search(text) or RX['opt_completed'].search(text))
    out['n_opt_steps'] = len(re.findall(r'Step number\s+\d+', text)) or \
        len(re.findall(r'---------- Cycle \d+ ----------', text))

    freqs = RX['freq'].findall(text)
    if freqs:
        vals = []
        for chunk in freqs:
            vals.extend(float(v) for v in chunk.split())
        out['frequencies'] = vals
        out['n_imag'] = len([v for v in vals if v < 0])
    m = RX['imag'].search(text)
    if m and out['n_imag'] is None:
        out['n_imag'] = int(m.group(1))

    exc = RX['exc'].findall(text)
    out['excitations'] = [
        dict(state=int(s), sym=sym, energy_ev=float(e), wavelength_nm=float(w),
             f=float(f))
        for s, sym, e, w, f in exc
    ]

    for key in ('zpe', 'e_thermal', 'enthalpy', 'gibbs'):
        m = RX[key].search(text)
        if m:
            out[key] = float(m.group(1))

    tail_after_term = ''
    m_term = list(re.finditer(r'Normal termination of Gaussian', text))
    if m_term:
        tail_after_term = text[m_term[-1].end():]
    if m_term and not re.search(r'^\s*#p?\s*[A-Za-z]', tail_after_term, re.M):
        out['status'] = 'normal'
    else:
        m = RX['error'].search(text)
        if m:
            out['status'] = 'error'
            out['error_link'] = os.path.basename(m.group(1))
            out['error_at'] = m.group(2).strip()
        elif 'SCF Done' in text or 'Frequencies --' in text:
            out['status'] = 'running'
    return out


def summarize(res):
    """一行文字摘要，给界面/报告用。"""
    bits = []
    if res['status'] == 'normal':
        bits.append('正常结束')
    elif res['status'] == 'error':
        bits.append('错误终止（%s）' % res.get('error_link', ''))
    elif res['status'] == 'running':
        bits.append('未结束/运行中')
    else:
        bits.append('无法判断')
    if res.get('energy') is not None:
        bits.append('E = %.6f Hartree' % res['energy'])
    if res.get('converged'):
        bits.append('优化收敛')
    if res.get('n_imag'):
        bits.append('%d 个虚频' % res['n_imag'])
    if res.get('excitations'):
        e1 = res['excitations'][0]
        bits.append('S1 %.2f eV / %.1f nm (f=%.3f)' % (
            e1['energy_ev'], e1['wavelength_nm'], e1['f']))
    return '；'.join(bits)


def parse_folder(folder):
    out = []
    if not os.path.isdir(folder):
        return out
    for fn in sorted(os.listdir(folder)):
        low = fn.lower()
        if low.startswith('job.') and low.endswith('.out'):
            continue          # Slurm 的 stdout，不是 Gaussian 输出
        if low.endswith(('.log', '.out')):
            try:
                out.append(parse_log(os.path.join(folder, fn)))
            except Exception as exc:  # noqa: BLE001
                out.append(dict(file=os.path.join(folder, fn), name=fn, status='error',
                                error_link='parse', error_at=str(exc), excitations=[]))
    return out
