# -*- coding: utf-8 -*-
"""把 TD-DFT 激发态画成 UV-Vis 谱图（棒状谱 + 展宽包络）。

横轴波长 / nm，纵轴相对吸光度（任意单位，由振子强度 f 高斯展宽得到）。
默认在能量域用 σ = 0.3 eV 展宽，比较接近溶液谱的带宽。
"""
from __future__ import annotations

import numpy as np
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams['font.family'] = ['Times New Roman', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['xtick.direction'] = 'in'
plt.rcParams['ytick.direction'] = 'in'
plt.rcParams['xtick.top'] = True
plt.rcParams['ytick.right'] = True

HC_EV_NM = 1239.841984          # E(eV) × λ(nm)


def broadening(excitations, sigma_ev=0.3, npts=1200):
    """返回 (λ 网格 / nm, 相对吸光度) —— 能量域高斯展宽后换算到波长轴。"""
    ex = [e for e in (excitations or [])]
    if not ex:
        return np.array([]), np.array([])
    lam_max = max(e['wavelength_nm'] for e in ex)
    lam_min = min(e['wavelength_nm'] for e in ex)
    lo = max(80.0, lam_min - 60.0)
    hi = min(1200.0, lam_max + 60.0)
    lam = np.linspace(lo, hi, npts)
    energy = HC_EV_NM / lam                     # eV
    y = np.zeros_like(lam)
    for e in ex:
        e0 = e['energy_ev']
        y += e['f'] * np.exp(-0.5 * ((energy - e0) / sigma_ev) ** 2)
    return lam, y


def uvvis_figure(excitations, title='', sigma_ev=0.3, n_states=None,
                 figsize=(7.2, 4.4), dpi=120):
    """棒状谱 + 展宽包络。返回 matplotlib Figure（失败返回 None）。"""
    ex = list(excitations or [])
    if not ex:
        return None
    if n_states:
        ex = [e for e in ex if e['state'] <= n_states]
    if not ex:
        return None

    lam, y = broadening(ex, sigma_ev=sigma_ev)
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)

    fmax = max(e['f'] for e in ex) or 1.0
    ymax = y.max() if y.size else fmax
    scale = (ymax / fmax) if fmax else 1.0
    for e in ex:
        if e['f'] < 1e-4:
            continue
        ax.vlines(e['wavelength_nm'], 0, e['f'] * scale,
                  color='0.6', linewidth=1.0, zorder=2)

    ax.plot(lam, y, color='#1f4e9c', linewidth=1.6, zorder=3,
            label='展宽谱（σ = %.2f eV）' % sigma_ev)

    bright = max(ex, key=lambda e: e['f'])
    if bright['f'] > 1e-4:
        ax.annotate('S%d  %.1f nm\nf = %.3f' % (bright['state'], bright['wavelength_nm'],
                                                bright['f']),
                    xy=(bright['wavelength_nm'], bright['f'] * scale),
                    xytext=(0.62, 0.82), textcoords='axes fraction',
                    fontsize=9, color='#1f4e9c',
                    arrowprops=dict(arrowstyle='->', color='#1f4e9c', lw=0.9,
                                    connectionstyle='arc3,rad=0.2'))

    ax.set_xlabel(r'$\lambda$ / nm')
    ax.set_ylabel('相对吸光度（任意单位）')
    ax.set_xlim(max(80.0, lam.min() - 10), min(1200.0, lam.max() + 10))
    ax.set_ylim(0, ymax * 1.25 if ymax else 1)
    ax.legend(fontsize=9, loc='upper right', frameon=False)
    if title:
        ax.set_title(title, fontsize=11.5)
    fig.tight_layout()
    return fig


def save_uvvis(excitations, path, title='', **kw):
    fig = uvvis_figure(excitations, title=title, **kw)
    if fig is None:
        return None
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path
