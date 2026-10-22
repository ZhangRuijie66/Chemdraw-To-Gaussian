/* 高斯计算工具前端逻辑 */
'use strict';

const $ = (id) => document.getElementById(id);
const state = { config: {}, molecules: [], catalogs: {}, selected: new Set(), lastResults: [] };

function toast(msg, ms = 2400) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove('show'), ms);
}

async function api(path, body) {
  const opt = { headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) {
    opt.method = 'POST';
    opt.body = JSON.stringify(body);
  }
  const r = await fetch(path, opt);
  return r.json();
}

function fillSelect(el, items, value) {
  el.innerHTML = items.map(([k, name]) => `<option value="${k}">${name}</option>`).join('');
  if (value !== undefined) el.value = value;
}

function setFields(cfg) {
  $('dataDir').value = cfg.input_dir || '';
  $('outDir').value = cfg.out_dir || '';
  $('job').value = cfg.job || 'opt_freq';
  $('functional').value = cfg.functional || 'PBE1PBE';
  $('basis').value = cfg.basis || 'def2TZVP';
  $('dispersion').value = cfg.dispersion || 'GD3BJ';
  $('solvent').value = cfg.solvent || '';
  $('solvationModel').value = cfg.solvation_model || 'IEFPCM';
  $('tdStates').value = cfg.td_states || 10;
  $('nproc').value = cfg.nproc || 32;
  $('mem').value = cfg.mem || '160GB';
  $('chkSuffix').value = cfg.chk_suffix || '_opt';
  $('nConformers').value = cfg.n_conformers || 1;
  $('forceField').value = cfg.force_field || 'MMFF94';
  $('trailing').value = cfg.trailing_blank_lines || 2;
  $('twoStep').checked = !!cfg.two_step;
  $('partition').value = cfg.partition || 'C032M0128G';
  $('qos').value = (cfg.qos === undefined || cfg.qos === null) ? 'low' : cfg.qos;
  $('ntasks').value = cfg.ntasks || 32;
  $('remoteDir').value = cfg.remote_dir || '~/g16jobs';
  $('walltime').value = (cfg.walltime === undefined || cfg.walltime === null) ? '5-00:00:00' : cfg.walltime;
  $('hpcHost').value = cfg.hpc_host || '';
  $('hpcUser').value = cfg.hpc_user || '';
  if (cfg.cluster) $('cluster').value = cfg.cluster;
  const out = cfg.out_dir || ((cfg.input_dir || '') + (cfg.input_dir ? '\gjf' : ''));
  if (out) $('makeHint').textContent = '生成到：' + out;
}

function readConfig() {
  return {
    input_dir: $('dataDir').value.trim(),
    out_dir: $('outDir').value.trim(),
    job: $('job').value,
    functional: $('functional').value,
    basis: $('basis').value,
    dispersion: $('dispersion').value,
    solvent: $('solvent').value,
    solvation_model: $('solvationModel').value,
    td_states: Number($('tdStates').value || 10),
    nproc: Number($('nproc').value || 32),
    mem: $('mem').value.trim() || '160GB',
    chk_suffix: $('chkSuffix').value.trim() || '_opt',
    n_conformers: Number($('nConformers').value || 1),
    force_field: $('forceField').value,
    trailing_blank_lines: Number($('trailing').value || 2),
    two_step: $('twoStep').checked,
    cluster: $('cluster').value,
    partition: $('partition').value.trim() || 'C032M0128G',
    qos: $('qos').value.trim() || 'low',
    ntasks: Number($('ntasks').value || 32),
    remote_dir: $('remoteDir').value.trim() || '~/g16jobs',
    walltime: $('walltime').value.trim(),
    hpc_host: $('hpcHost').value.trim(),
    hpc_user: $('hpcUser').value.trim(),
  };
}

function renderSubmitMols(mols) {
  const box = $('submitMols');
  if (!box) return;
  const ok = (mols || []).filter((m) => m.ok);
  if (!ok.length) {
    box.innerHTML = '<span class="hint">先扫描分子目录</span>';
    return;
  }
  box.innerHTML = ok.map((m) =>
    '<label><input type="checkbox" class="submchk" data-name="' + m.name + '">' +
    m.name + '</label>').join('');
}

function selectedSubmitMols() {
  return [...document.querySelectorAll('#submitMols input.submchk')]
    .filter((c) => c.checked).map((c) => c.dataset.name);
}

function gjfMatchKind(name, kind) {
  const low = name.toLowerCase();
  if (kind === 'all') return true;
  if (kind === 'opt') return !/_(td|freq|gs|fc)\.gjf$/.test(low);
  return low.endsWith('_' + kind + '.gjf');
}

function gjfMatchMol(name, mol) {
  let base = name.toLowerCase().replace(/\.gjf$/, '');
  base = base.replace(/_(td|freq|gs|fc)$/, '');
  return base === mol.toLowerCase();
}

function renderMolecules(mols) {
  renderSubmitMols(mols);
  const box = $('molList');
  if (!mols || !mols.length) {
    box.innerHTML = '<p class="hint">目录里没有找到 .cdxml / .cdx / .mol 文件。</p>';
    return;
  }
  state.selected = new Set();          // 默认全不选，由用户自己勾
  box.innerHTML = mols.map((m) => {
    const meta = m.ok
      ? `${m.formula} · 电荷 ${m.charge > 0 ? '+' + m.charge : m.charge} · ${m.heavy_atoms} 重原子`
      : `<span class="err">${m.error}</span>`;
    return `<label class="molrow" title="${m.path}">
      <input type="checkbox" data-path="${m.path}" ${m.ok ? '' : 'disabled'}>
      <span class="name">${m.name}</span>
      <span class="meta">${meta}</span>
    </label>`;
  }).join('');
  box.querySelectorAll('input[type=checkbox]').forEach((cb) => {
    cb.addEventListener('change', () => {
      const p = cb.dataset.path;
      if (cb.checked) state.selected.add(p); else state.selected.delete(p);
    });
  });
  box.querySelectorAll('.name').forEach((el) => {
    el.addEventListener('click', (ev) => {
      ev.preventDefault();
      const row = el.closest('.molrow');
      const p = row.querySelector('input').dataset.path;
      preview(p);
    });
  });
}

async function loadState() {
  const s = await api('/api/state');
  if (!s.ok) { toast('加载失败：' + (s.error || '')); return; }
  state.config = s.config;
  state.catalogs = s.catalogs;
  $('verTag').textContent = 'v' + (s.version || '?') + ' · ' + (s.build || '');
  const c = s.catalogs;
  fillSelect($('job'), c.jobs.map(([k, name, d]) => [k, `${name}`]), s.config.job);
  fillSelect($('functional'), c.functionals.map(([k, name, d]) => [k, `${name}`]), s.config.functional);
  fillSelect($('basis'), c.basis_sets.map(([k, name, d]) => [k, `${name}`]), s.config.basis);
  fillSelect($('dispersion'), c.dispersions.map(([k, name, d]) => [k, name]), s.config.dispersion);
  fillSelect($('solvent'), c.solvents.map(([k, name]) => [k, name]), s.config.solvent);
  fillSelect($('solvationModel'), c.solvation_models.map(([k, name]) => [k, name]), s.config.solvation_model);
  fillSelect($('forceField'), [['MMFF94', 'MMFF94'], ['UFF', 'UFF']], s.config.force_field);
  fillSelect($('cluster'), (c.clusters || []).map(([k, name, login, data, note]) => [k, `${name}（${login}）`]), s.config.cluster);
  setFields(s.config);
  if (!s.config.hpc_host) {
    const cl = (c.clusters || []).find((x) => x[0] === (s.config.cluster || 'wm1'));
    if (cl) $('hpcHost').value = cl[2];
  }
  $('routeText').textContent = s.route;
  renderSession(s.hpc_session);
  const q = new URLSearchParams(location.search);
  if (q.get('dir')) parseLogs(q.get('dir'));
  renderMolecules(s.molecules);
  if (s.molecules && s.molecules.length) preview(s.molecules.find((m) => m.ok)?.path);
}

async function scan() {
  const dir = $('dataDir').value.trim();
  if (!dir) { toast('先选择目录'); return; }
  const s = await api('/api/scan', { dir });
  if (!s.ok) { toast('扫描失败：' + (s.error || '')); return; }
  state.config = s.config;
  state.molecules = s.molecules;
  renderMolecules(s.molecules);
  $('routeText').textContent = s.route;
  toast(`找到 ${s.molecules.length} 个文件`);
}

async function preview(path) {
  if (!path) return;
  const r = await api('/api/preview', { config: readConfig(), path });
  if (!r.ok) { toast('预览失败：' + (r.error || '')); return; }
  state.lastPreview = r.result;
  const pre = $('preview');
  pre.textContent = r.result.text;
  $('routeText').textContent = r.result.route.startsWith('#') ? r.result.route : '#p ' + r.result.route;
  pre.scrollTop = 0;
}

async function make() {
  const cfg = readConfig();
  const paths = [...state.selected];
  if (!paths.length) { toast('先勾选要生成的分子'); return; }
  const btn = $('btnMake');
  btn.disabled = true; btn.textContent = '生成中…';
  try {
    const r = await api('/api/make', { config: cfg, paths });
    if (!r.ok) { toast('生成失败：' + (r.error || '')); return; }
    state.lastResults = r.results;
    state.gjfPaths = r.results.filter((x) => !x.error).flatMap((x) => x.files);
    const rows = r.results.map((x) => {
      if (x.error) return `<div class="bad">✗ ${x.name}：${x.error}</div>`;
      return `<div class="ok">✓ ${x.name} → ${x.files.map((f) => f.split(/[\\/]/).pop()).join(', ')}（${x.atoms} 原子，${x.force_field}）</div>`;
    }).join('');
    $('results').innerHTML = rows + `<p class="hint">输出目录：${r.out_dir}　成功 ${r.n_ok}，失败 ${r.n_fail}</p>`;
    if (r.results.length) preview(r.results[0].path);
    toast(`已生成 ${r.n_ok} 个文件`);
  } finally {
    btn.disabled = false; btn.textContent = '生成 .gjf';
  }
}

async function save() {
  const s = await api('/api/settings', { config: readConfig() });
  if (!s.ok) { toast('保存失败'); return; }
  toast('已存为默认设置');
}

$('btnBrowse').onclick = async () => {
  const r = await api('/api/pickdir', { initial: $('dataDir').value.trim() });
  if (r.ok && r.path) { $('dataDir').value = r.path; scan(); }
};
$('btnBrowseOut').onclick = async () => {
  const r = await api('/api/pickdir', { initial: $('outDir').value.trim() || $('dataDir').value.trim() });
  if (r.ok && r.path) $('outDir').value = r.path;
};
$('btnScan').onclick = scan;
$('btnMake').onclick = make;
$('btnSave').onclick = save;
$('btnAll').onclick = () => {
  document.querySelectorAll('#molList input[type=checkbox]').forEach((cb) => {
    if (!cb.disabled) { cb.checked = true; state.selected.add(cb.dataset.path); }
  });
};
$('btnNone').onclick = () => {
  document.querySelectorAll('#molList input[type=checkbox]').forEach((cb) => { cb.checked = false; });
  state.selected.clear();
};
$('cluster').addEventListener('change', () => {
  const c = state.catalogs && state.catalogs.clusters
    ? state.catalogs.clusters.find((x) => x[0] === $('cluster').value) : null;
  if (c) $('hpcHost').value = c[2];
  // 切换集群时自动带出该集群的默认分区 / QOS / 墙钟
  const d = state.catalogs && state.catalogs.cluster_defaults
    ? state.catalogs.cluster_defaults[$('cluster').value] : null;
  if (d) {
    $('partition').value = d.partition || '';
    $('qos').value = d.qos || '';
    $('walltime').value = d.walltime || '';
  }
});
$('job').addEventListener('change', () => {
  const map = { td: 'td', vibronic: 'gs', freq: 'freq' };
  const k = map[$('job').value];
  if (k) $('submitKind').value = k;
  else if ($('job').value === 'opt_freq' || $('job').value === 'opt') $('submitKind').value = 'opt';
  preview(state.lastPreview?.path);
});
['functional', 'basis', 'dispersion', 'solvent', 'solvationModel', 'tdStates',
 'chkSuffix', 'trailing', 'twoStep', 'nproc', 'mem'].forEach((id) => {
  $(id).addEventListener('change', () => { if (state.lastPreview) preview(state.lastPreview.path); });
});

loadState().catch((e) => toast('初始化失败：' + e.message));

// ---------------------------------------------------------------- 超算
// 说明：JS 字符串里的换行统一用 NL，避免源码里出现真实换行。
const NL = String.fromCharCode(10);

function hpcPayload() {
  return {
    config: readConfig(),
    host: $('hpcHost').value.trim(),
    user: $('hpcUser').value.trim(),
    password: $('hpcPwd').value,
    otp: $('hpcOtp').value.trim(),
    port: 22,
    remote_dir: $('remoteDir').value.trim() || '~/g16jobs',
    kind: $('submitKind').value,
  };
}

function _exText(e) {
  if (!e) return '—';
  const dark = e.f < 0.01 ? ' <span style="color:#9ca3af">(暗)</span>' : '';
  return 'S' + e.state + ' ' + e.wavelength_nm.toFixed(1) + ' nm (f=' + e.f.toFixed(3) + ')' + dark;
}

function renderLogs(results, dir) {
  const box = $('logResults');
  if (!results || !results.length) {
    box.innerHTML = '<p class="hint">' + (dir || '') + ' 里没有 .log/.out 文件。</p>';
    return;
  }
  const rows = results.map((r) => {
    const st = r.status === 'normal' ? '<span class="ok">正常</span>'
      : (r.status === 'error' ? '<span class="bad">错误(' + (r.error_link || '') + ')</span>'
      : '<span>' + (r.status === 'running' ? '未结束' : '未知') + '</span>');
    const exs = r.excitations || [];
    const s1 = exs.find((e) => e.state === 1) || exs[0];
    const bright = exs.reduce((a, b) => (b.f > (a ? a.f : -1) ? b : a), null);
    const ex = _exText(s1);
    const br = _exText(bright);
    return '<tr><td>' + r.name + '</td><td>' + st + '</td>' +
      '<td>' + (r.energy != null ? r.energy.toFixed(6) : '—') + '</td>' +
      '<td>' + (r.converged ? '是' : (r.status === 'running' ? '…' : '否')) + '</td>' +
      '<td>' + (r.n_imag != null ? r.n_imag : '—') + '</td>' +
      '<td>' + ex + '</td><td>' + br + '</td>' +
      '<td>' + ((r.excitations && r.excitations.length)
        ? '<a class="uvlink" data-path="' + r.file + '">UV-Vis 图</a>' : '—') + '</td></tr>';
  }).join('');
  box.innerHTML = '<table style="width:100%;border-collapse:collapse;font-size:12.5px">' +
    '<thead><tr style="color:#4b5563;text-align:left"><th>分子</th><th>状态</th><th>E / Hartree</th>' +
    '<th>优化</th><th>虚频</th><th>TD-DFT S1</th><th>最强吸收跃迁</th><th>图</th></tr></thead>' +
    '<tbody>' + rows + '</tbody></table>' +
    '<p class="hint">目录：' + (dir || '') + '　（f≈0 表示对称性禁阻的暗态，比较实验 λmax 应看「最强吸收跃迁」）</p>' +
    '<div id="uvvisBox" style="margin-top:10px"></div>';
  box.querySelectorAll('a.uvlink').forEach((a) => {
    a.style.cursor = 'pointer';
    a.style.color = '#2563eb';
    a.style.textDecoration = 'underline';
    a.addEventListener('click', (ev) => {
      ev.preventDefault();
      const p = a.dataset.path;
      const name = p.split(/[\\/]/).pop().replace(/\.log$/i, '');
      $('uvvisBox').innerHTML = '<div class="hint">正在画 ' + name + ' 的 UV-Vis 图…</div>' +
        '<img alt="UV-Vis" style="max-width:100%;border:1px solid #e3e7ef;border-radius:10px" ' +
        'src="/api/logs/uvvis?save=1&path=' + encodeURIComponent(p) + '&title=' +
        encodeURIComponent(name + '  TD-DFT') + '">';
    });
  });
}

async function parseLogs(dir) {
  const r = await api('/api/logs/parse', { dir });
  if (!r.ok) { toast('解析失败：' + (r.error || '')); return; }
  renderLogs(r.results, r.dir);
  toast('解析了 ' + r.results.length + ' 个日志');
}

const hpcBuf = [];

function _fmtSize(n) {
  if (n == null) return '—';
  if (n >= 1048576) return (n / 1048576).toFixed(1) + ' MB';
  if (n >= 1024) return (n / 1024).toFixed(1) + ' KB';
  return n + ' B';
}

function renderLocalGjf(files, dir, action) {
  const box = $('localPick');
  if (!files || !files.length) {
    box.innerHTML = '<p class="hint">' + (dir || '输出目录') + ' 里没有 .gjf 文件，先点「生成 .gjf」。</p>';
    return;
  }
  const kind = $('submitKind').value;
  const matchKind = (name) => {
    const low = name.toLowerCase();
    if (kind === 'all') return true;
    if (kind === 'opt') return !/_(td|freq|gs|fc)\.gjf$/.test(low);
    return low.endsWith('_' + kind + '.gjf');
  };
  const rows = files.map((f) => '<tr>' +
    '<td><input type="checkbox" class="locchk" data-path="' + f.path + '"' +
    (matchKind(f.name) ? ' checked' : '') + '></td>' +
    '<td>' + f.name + '</td><td>' + _fmtSize(f.size) + '</td>' +
    '<td>' + (f.mtime || '—') + '</td></tr>').join('');
  const btnText = action === 'bundle' ? '生成提交包' : '上传并提交';
  box.innerHTML = '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">' +
    '<b style="font-size:13px">选择要打包/提交的 .gjf（' + files.length + ' 个）</b>' +
    '<button class="btn" id="btnLocAll" style="padding:4px 10px">全选</button>' +
    '<button class="btn primary" id="btnLocGo" style="padding:4px 10px">' + btnText + '</button>' +
    '<button class="btn" id="btnLocCancel" style="padding:4px 10px">取消</button>' +
    '<span class="hint" style="margin:0">' + (dir || '') + '</span></div>' +
    '<div style="max-height:220px;overflow:auto;border:1px solid #e8ecf4;border-radius:10px">' +
    '<table style="width:100%;border-collapse:collapse;font-size:12.5px">' +
    '<thead><tr style="color:#4b5563;text-align:left"><th style="width:32px"></th>' +
    '<th>文件</th><th style="width:90px">大小</th><th style="width:150px">最后修改</th></tr></thead>' +
    '<tbody>' + rows + '</tbody></table></div>';
  $('btnLocAll').onclick = () => {
    const cbs = box.querySelectorAll('input.locchk');
    const all = [...cbs].every((c) => c.checked);
    cbs.forEach((c) => { c.checked = !all; });
  };
  $('btnLocCancel').onclick = () => { box.innerHTML = ''; };
  box.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  $('btnLocGo').onclick = async () => {
    const paths = [...box.querySelectorAll('input.locchk')]
      .filter((c) => c.checked).map((c) => c.dataset.path);
    if (!paths.length) { toast('至少选一个 .gjf'); return; }
    box.innerHTML = '';
    if (action === 'bundle') {
      const r = await api('/api/hpc/bundle', { config: readConfig(), paths,
                                              kind: $('submitKind').value });
      if (!r.ok) { toast('生成提交包失败：' + (r.error || '')); return; }
      hpcLog('提交包（未提交，可手动上传）：' + r.bundle.root + NL +
             (r.bundle.zip ? '压缩包：' + r.bundle.zip + NL : '') +
             '文件：' + r.bundle.names.join(', '));
      toast('提交包已生成');
    } else {
      await hpcCall('/api/hpc/submit', { paths, kind: $('submitKind').value });
    }
  };
}

function renderRemoteFiles(files, dir, kind) {
  const box = $('remoteFiles');
  kind = kind || 'log';
  if (!files || !files.length) {
    box.innerHTML = '<p class="hint">' + (dir || '远程目录') + ' 里没有 ' +
      (kind === 'chk' ? '.chk' : '.log / .out / .err') + ' 文件。</p>';
    return;
  }
  const btnText = kind === 'chk' ? '转换并下载选中' : '下载选中';
  const rows = files.map((f, i) => '<tr>' +
    '<td><input type="checkbox" class="remchk" data-name="' + f.name + '" checked></td>' +
    '<td>' + f.name + '</td><td>' + _fmtSize(f.size) + '</td>' +
    '<td>' + (f.mtime || '—') + '</td></tr>').join('');
  box.innerHTML = '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">' +
    '<b style="font-size:13px">远程文件（' + files.length + ' 个）</b>' +
    '<button class="btn" id="btnRemAll" style="padding:4px 10px">全选</button>' +
    '<button class="btn primary" id="btnRemDl" style="padding:4px 10px">' + btnText + '</button>' +
    '<span class="hint" style="margin:0">' + (dir || '') + '</span></div>' +
    '<div style="max-height:220px;overflow:auto;border:1px solid #e8ecf4;border-radius:10px">' +
    '<table style="width:100%;border-collapse:collapse;font-size:12.5px">' +
    '<thead><tr style="color:#4b5563;text-align:left"><th style="width:32px"></th>' +
    '<th>文件</th><th style="width:90px">大小</th><th style="width:150px">最后修改</th></tr></thead>' +
    '<tbody>' + rows + '</tbody></table></div>';
  $('btnRemAll').onclick = () => {
    const cbs = box.querySelectorAll('input.remchk');
    const all = [...cbs].every((c) => c.checked);
    cbs.forEach((c) => { c.checked = !all; });
  };
  $('btnRemDl').onclick = async () => {
    const names = [...box.querySelectorAll('input.remchk')]
      .filter((c) => c.checked).map((c) => c.dataset.name);
    if (!names.length) { toast('先勾选要处理的文件'); return; }
    if (kind === 'chk') {
      hpcLog('正在转换并下载 ' + names.length + ' 个 .chk …');
      await hpcCall('/api/hpc/chk', { names });
    } else {
      await hpcCall('/api/hpc/fetch', { names });
    }
    renderRemoteFiles([], dir, kind);
  };
}

function hpcLog(text) {
  const now = new Date();
  const stamp = '[' + String(now.getHours()).padStart(2, '0') + ':' +
    String(now.getMinutes()).padStart(2, '0') + ':' +
    String(now.getSeconds()).padStart(2, '0') + '] ';
  const lines = String(text || '—').split(String.fromCharCode(10));
  lines.forEach((ln, i) => hpcBuf.push((i === 0 ? stamp : '    ') + ln));
  if (hpcBuf.length > 3000) hpcBuf.splice(0, hpcBuf.length - 3000);
  const pre = $('hpcOut');
  pre.textContent = hpcBuf.join(String.fromCharCode(10));
  pre.scrollTop = pre.scrollHeight;
}

function hpcClear() {
  hpcBuf.length = 0;
  $('hpcOut').textContent = '—';
}

function renderSession(sess) {
  const el = $('hpcSession');
  if (sess && sess.active) {
    el.textContent = '已登录：' + sess.user + '@' + sess.host + '（连接保持中，后续操作不用再输 OTP）';
  } else {
    el.textContent = '未登录（首次操作需密码 + OTP；登录后连接保持，断开或超时才需重输）';
  }
}

async function hpcBundle() {
  const paths = state.gjfPaths || [];
  if (!paths.length) { toast('先生成 .gjf 文件'); return; }
  const r = await api('/api/hpc/bundle', { config: readConfig(), paths,
                                        kind: $('submitKind').value });
  if (!r.ok) { toast('生成提交包失败：' + (r.error || '')); return; }
  const first = Object.keys(r.bundle.scripts)[0];
  hpcLog('提交包：' + r.bundle.root + NL +
         (r.bundle.zip ? '压缩包：' + r.bundle.zip + NL : '') +
         NL + '—— job_' + first + '.sh ——' + NL + (r.bundle.scripts[first] || ''));
  toast('提交包已生成');
}

async function hpcCall(path, extra) {
  const btn = document.activeElement;
  if (btn) btn.disabled = true;
  hpcLog('连接 ' + ($('hpcHost').value || '…') + ' …');
  try {
    const r = await api(path, Object.assign(hpcPayload(), extra || {}));
    if (!r.ok) { hpcLog('失败：' + (r.error || '')); toast('操作失败'); return; }
    if (path.endsWith('/login')) {
      $('hpcOtp').value = '';  // OTP 一次性，登录成功后清空
      hpcLog('登录成功（连接已保持）：' + NL + r.output);
    } else if (path.endsWith('/status')) {
      let txt = '排队/运行中：' + NL + (r.squeue || '(空)');
      if (r.history_available) {
        txt += NL + NL + '近两天已完成作业：' + NL + (r.history || '(没有记录)');
      }
      hpcLog(txt);
    } else if (path.endsWith('/ls')) {
      const label = r.kind === 'chk' ? '.chk' : '日志';
      if (!r.files || !r.files.length) {
        const why = r.exists === false
          ? '远程目录不存在：' + (r.root || r.dir) + '（先点一次「上传并提交」）'
          : '目录存在（' + (r.root || r.dir) + '），但没有 ' + label + ' 文件；' +
            '可能还没算完，或文件在更深层的子目录里。';
        $('remoteFiles').innerHTML = '<p class="hint">' + why + '</p>';
        hpcLog('读取远程目录：' + (r.root || r.dir) + NL + why);
        return;
      }
      renderRemoteFiles(r.files, r.dir, r.kind);
      hpcLog('读取远程目录：' + (r.root || r.dir) + NL + '共 ' + r.files.length +
             ' 个 ' + label + '文件，勾选后点「' +
             (r.kind === 'chk' ? '转换并下载选中' : '下载选中') + '」。');
    } else if (path.endsWith('/chk')) {
      const lines = (r.entries || []).map((e) =>
        (e.ok ? '✓ ' : '✗ ') + e.name + '  (' + (e.chk_size / 1048576).toFixed(1) + ' MB)' +
        (e.ok ? ' → ' + e.fchk + '  ' + (e.fchk_size / 1048576).toFixed(1) + ' MB'
              : '  转换失败：' + (e.message || '').split(NL)[0]));
      hpcLog('远程目录里的 .chk：' + NL + (lines.length ? lines.join(NL) : '(没有找到)') +
             NL + NL + '已下载到：' + (r.dir || '') + NL +
             (r.files || []).map((f) => f.split(/[\/]/).pop()).join(NL));
    } else if (path.endsWith('/fetch')) {
      hpcLog('已下载 ' + r.files.length + ' 个文件到：' + NL + r.dir + NL + r.files.join(NL));
      state.logDir = r.dir;
      parseLogs(r.dir);
    } else if (path.endsWith('/submit')) {
      const lines = Object.entries(r.jobs).map(([n, j]) =>
        (j.ok ? '✓ ' + n + ' → job ' + j.jobid : '✗ ' + n + '：' + j.output));
      const depLines = Object.entries(r.deps || {}).map(([n, d]) =>
        n + '  ← 依赖 job ' + d.join(',') + '（afterok）');
      const autoNote = r.auto ? NL + '（没有选中具体文件，自动使用输出目录里的 .gjf）' : '';
      hpcLog('已提交到 ' + r.remote + NL + lines.join(NL) + autoNote +
             (r.bundle ? NL * 2 + '本地留档：' + r.bundle : '') +
             (depLines.length ? NL + NL + '依赖关系：' + NL + depLines.join(NL) : '') +
             NL + NL + (r.squeue || ''));
    }
    if (r.session) renderSession(r.session);
    toast('完成');
  } finally {
    if (btn) btn.disabled = false;
  }
}

$('btnClearOut').onclick = hpcClear;
$('btnParseLocal').onclick = () => {
  const cfg = readConfig();
  const out = cfg.out_dir || (cfg.input_dir ? cfg.input_dir + '\\gjf' : '');
  const d = state.logDir || (out ? out + '\\logs' : '') || cfg.input_dir;
  parseLogs(d);
};
async function pickOrDirect(action) {
  const cfg = readConfig();
  const od = cfg.out_dir || (cfg.input_dir ? cfg.input_dir + '\\gjf' : '');
  const r = await api('/api/gjf/list', { config: cfg, dir: od });
  if (!r.ok) { toast('读取失败：' + (r.error || '')); return; }
  const mols = selectedSubmitMols();
  const kind = $('submitKind').value;
  if (!mols.length) { renderLocalGjf(r.files, r.dir, action); return; }
  const files = (r.files || []).filter((f) =>
    mols.some((m) => gjfMatchMol(f.name, m)) && gjfMatchKind(f.name, kind));
  if (!files.length) {
    toast('勾选的分子（' + mols.join('、') + '）里没有「' + kind + '」类型的 .gjf，请先生成');
    return;
  }
  const paths = files.map((f) => f.path);
  if (action === 'bundle') {
    const b = await api('/api/hpc/bundle', { config: cfg, paths, kind });
    if (!b.ok) { toast('生成提交包失败：' + (b.error || '')); return; }
    hpcLog('提交包（未提交，可手动上传）：' + b.bundle.root + NL +
           (b.bundle.zip ? '压缩包：' + b.bundle.zip + NL : '') +
           '文件：' + b.bundle.names.join(', '));
    toast('提交包已生成');
  } else {
    await hpcCall('/api/hpc/submit', { paths, kind });
  }
}

$('btnBundle').onclick = () => pickOrDirect('bundle');
$('btnLogin').onclick = () => hpcCall('/api/hpc/login');
$('btnSubmit').onclick = () => pickOrDirect('submit');
$('btnStatus').onclick = () => hpcCall('/api/hpc/status');
$('btnFetch').onclick = () => hpcCall('/api/hpc/ls');
$('btnChk').onclick = () => hpcCall('/api/hpc/ls', { suffix: 'chk' });
$('btnLogout').onclick = async () => {
  const r = await api('/api/hpc/logout', {});
  if (r.ok) { renderSession(r.session); hpcLog('已断开连接'); toast('已断开'); }
};

// 调试用：?pick=1 自动打开「提交文件选择」面板，方便检查渲染
if (new URLSearchParams(location.search).get('pick') === '1') {
  setTimeout(() => { try { $('btnSubmit').onclick(); } catch (e) {} }, 600);
}
