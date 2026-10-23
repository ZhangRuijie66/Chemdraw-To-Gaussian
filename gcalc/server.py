# -*- coding: utf-8 -*-
"""高斯计算工具 —— 本地网页服务。

启动后打开浏览器；所有结构转换都在本机完成，不联网、不上传数据。
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB_DIR = os.path.join(ROOT, 'web')
sys.path.insert(0, ROOT)

from gcalc import __version__, BUILD, batch, embed, glog, hpc, methods, plotting  # noqa: E402

SETTINGS_FILE = os.path.join(ROOT, 'settings.json')
STATE = {'config': None, 'molecules': []}
# 持久 SSH 会话：登录一次后复用连接，避免每次操作都要输 OTP
HPC_SESSION = {'cli': None, 'host': '', 'user': '', 'port': 22, 'since': 0.0}
HPC_LOCK = threading.Lock()
LOCK = threading.Lock()


# ---------------------------------------------------------------- 设置
def load_settings():
    cfg = batch.default_config()
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as fh:
                saved = json.load(fh)
            for k in batch.PERSIST_KEYS:
                if k in saved:
                    cfg[k] = saved[k]
        except (OSError, ValueError):
            pass
    return cfg


def save_settings(cfg):
    data = {k: cfg.get(k) for k in batch.PERSIST_KEYS if k in cfg}
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write('\n')


def _coerce(cfg, payload):
    """把表单传来的字符串转成合适的类型；只保留已知字段。"""
    base = load_settings() if cfg is None else dict(cfg)
    for k in batch.PERSIST_KEYS:
        if k not in payload:
            continue
        v = payload[k]
        ref = batch.DEFAULT_CONFIG.get(k)
        if isinstance(ref, bool):
            base[k] = bool(v) if not isinstance(v, str) else v.lower() in ('1', 'true', 'yes', 'on')
        elif isinstance(ref, int) and not isinstance(ref, bool):
            try:
                base[k] = int(float(v))
            except (TypeError, ValueError):
                pass
        else:
            base[k] = v
    # 额外字段
    for k in ('multiplicity',):
        if k in payload:
            try:
                base[k] = int(payload[k])
            except (TypeError, ValueError):
                base[k] = 1
    return base


def _config_from(payload=None):
    cfg = load_settings()
    if payload:
        cfg = _coerce(cfg, payload)
    return cfg



SUBMIT_KINDS = {
    'all': '全部 .gjf',
    'opt': '优化 / 频率（不含 _td/_gs/_fc）',
    'td': 'TD-DFT 单点（_td.gjf）',
    'gs': '振动分辨第一步（_gs.gjf）',
    'fc': '振动分辨第二步（_fc.gjf）',
    'freq': '单独频率（_freq.gjf）',
}


def _dep_base(name):
    """返回这个作业依赖的基态作业名：_td → 去掉 _td；_fc → 同一个分子的 _gs；其余无依赖。"""
    low = name.lower()
    if low.endswith('_td'):
        return name[:-3]
    if low.endswith('_fc'):
        return name[:-3] + '_gs'
    return None


def _filter_gjf(paths, kind):
    """按提交类型筛 .gjf：opt 排除 _td/_gs/_fc，其余按后缀取。"""
    kind = (kind or 'all').lower()
    if kind == 'all':
        return paths
    if kind == 'opt':
        return [p for p in paths
                if not re.search(r'_(td|freq|gs|fc)\.gjf$', os.path.basename(p).lower())]
    return [p for p in paths
            if os.path.basename(p).lower().endswith('_%s.gjf' % kind)]


def _gjf_paths(cfg, payload_paths):
    """请求里没给路径时，自动用输出目录里的 .gjf（省一步「生成」）。"""
    paths = [p for p in (payload_paths or []) if os.path.isfile(p)]
    if paths:
        return paths
    od = batch.out_dir_for(cfg)
    if os.path.isdir(od):
        paths = [os.path.join(od, f) for f in sorted(os.listdir(od))
                 if f.lower().endswith('.gjf')]
    return paths

def _hpc_session_info():
    cli = HPC_SESSION.get('cli')
    alive = bool(cli and cli.is_alive())
    if cli and not alive:
        try:
            cli.close()
        except Exception:  # noqa: BLE001
            pass
        HPC_SESSION.update(cli=None, host='', user='', since=0.0)
    return dict(active=alive, host=HPC_SESSION.get('host', ''),
                user=HPC_SESSION.get('user', ''), since=HPC_SESSION.get('since', 0.0))


def _hpc_client(payload):
    """有存活会话就直接复用；否则用请求里的密码 + OTP 新登录并保存会话。"""
    with HPC_LOCK:
        info = _hpc_session_info()
        if info['active']:
            return HPC_SESSION['cli'], info
        host = (payload.get('host') or '').strip()
        user = (payload.get('user') or '').strip()
        pwd = payload.get('password') or ''
        otp = payload.get('otp') or ''
        port = int(payload.get('port') or 22)
        if not host or not user or not pwd:
            raise RuntimeError('还没有登录：请填集群地址、学号和密码（OTP 只需登录时输一次）')
        cli = hpc.HpcClient(host, user, pwd, otp, port)
        cli.connect()
        HPC_SESSION.update(cli=cli, host=host, user=user, port=port, since=time.time())
        return cli, _hpc_session_info()


def pick_folder(initial=None):
    """弹出系统「选择文件夹」窗口（子进程 tkinter），返回绝对路径。"""
    auto = os.environ.get('GCALC_PICK_AUTO')
    if auto:
        return os.path.normpath(auto) if os.path.isdir(auto) else ''
    code = (
        "import sys, tkinter as tk\n"
        "from tkinter import filedialog\n"
        "root = tk.Tk(); root.withdraw()\n"
        "try:\n"
        "    root.attributes('-topmost', True)\n"
        "except Exception:\n"
        "    pass\n"
        "root.update()\n"
        "kwargs = dict(parent=root, title='选择文件夹')\n"
        "init = sys.argv[1] if len(sys.argv) > 1 else ''\n"
        "if init:\n"
        "    kwargs['initialdir'] = init\n"
        "p = filedialog.askdirectory(**kwargs)\n"
        "root.destroy()\n"
        "sys.stdout.write(p or '')\n"
    )
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    try:
        out = subprocess.run([sys.executable, '-c', code, initial or ''],
                             capture_output=True, timeout=900, env=env)
    except (OSError, subprocess.SubprocessError):
        return ''
    txt = out.stdout.decode('utf-8', 'replace').strip()
    if not txt:
        return ''
    return os.path.normpath(txt) if os.path.isdir(txt) else ''


# ---------------------------------------------------------------- 摘要
def _summary(cfg, molecules=None):
    return dict(
        ok=True,
        version=__version__,
        build=BUILD,
        config=cfg,
        molecules=molecules if molecules is not None else STATE['molecules'],
        out_dir=batch.out_dir_for(cfg),
        catalogs=dict(
            functionals=methods.FUNCTIONALS,
            basis_sets=methods.BASIS_SETS,
            jobs=methods.JOBS,
            dispersions=methods.DISPERSIONS,
            solvents=methods.SOLVENTS,
            solvation_models=methods.SOLVATION_MODELS,
            force_fields=[[k, n, d] for k, n, d in embed.FORCE_FIELDS],
            clusters=[[c[0], c[1], c[2], c[3], c[4]] for c in hpc.CLUSTERS],
            cluster_defaults={c[0]: hpc.cluster_defaults(c[0]) for c in hpc.CLUSTERS},
        ),
        hpc_session=_hpc_session_info(),
        route=methods.route_line(cfg),
        method=methods.method_summary(cfg),
    )


class Handler(BaseHTTPRequestHandler):
    server_version = 'GCalc/1.0'

    def log_message(self, fmt, *args):  # noqa: A003
        pass

    # ---------------------------------------------------------- 基础
    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str))

    def _error(self, exc):
        self._json(dict(ok=False, error=str(exc),
                        trace=traceback.format_exc(limit=6)), 500)

    def _body(self):
        n = int(self.headers.get('Content-Length') or 0)
        if not n:
            return {}
        raw = self.rfile.read(n)
        try:
            return json.loads(raw.decode('utf-8'))
        except ValueError:
            return {}

    def _uvvis(self):
        """GET /api/logs/uvvis?path=<log 路径>&title=...&sigma=0.3 → PNG"""
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        path = (q.get('path') or [''])[0]
        if not path or not os.path.isfile(path):
            self._send(404, b'log not found', 'text/plain; charset=utf-8')
            return
        res = glog.parse_log(path)
        ex = res.get('excitations') or []
        if not ex:
            self._send(404, b'no excitations in this log', 'text/plain; charset=utf-8')
            return
        title = (q.get('title') or [''])[0]
        try:
            sigma = float((q.get('sigma') or ['0.3'])[0])
        except ValueError:
            sigma = 0.3
        import io as _io
        fig = plotting.uvvis_figure(ex, title=title, sigma_ev=sigma)
        if fig is None:
            self._send(500, b'plot failed', 'text/plain; charset=utf-8')
            return
        buf = _io.BytesIO()
        fig.savefig(buf, format='png', dpi=200)
        if q.get('save'):
            try:
                fig.savefig(os.path.splitext(path)[0] + '_uvvis.png', dpi=200)
            except OSError:
                pass
        import matplotlib.pyplot as _plt
        _plt.close(fig)
        self._send(200, buf.getvalue(), 'image/png')

    # ---------------------------------------------------------- 路由
    def do_GET(self):
        try:
            if self.path == '/api/state':
                cfg = _config_from()
                mols = STATE['molecules']
                if cfg.get('input_dir') and os.path.isdir(cfg['input_dir']):
                    try:
                        mols = batch.scan(cfg['input_dir'])
                        STATE['molecules'] = mols
                    except Exception:  # noqa: BLE001
                        mols = []
                self._json(_summary(cfg, mols))
                return
            if self.path.startswith('/api/logs/uvvis'):
                self._uvvis()
                return
            self._static(self.path)
        except Exception as exc:  # noqa: BLE001
            self._error(exc)

    def do_POST(self):
        try:
            payload = self._body()
            path = self.path.split('?')[0]
            if path == '/api/scan':
                folder = payload.get('dir') or ''
                if not os.path.isdir(folder):
                    self._json(dict(ok=False, error='目录不存在：%s' % folder))
                    return
                mols = batch.scan(folder)
                STATE['molecules'] = mols
                cfg = _config_from()
                cfg['input_dir'] = folder
                self._json(_summary(cfg, mols))
                return

            if path == '/api/pickdir':
                p = pick_folder(payload.get('initial'))
                self._json(dict(ok=True, path=p))
                return

            if path == '/api/settings':
                cfg = _config_from(payload.get('config') or {})
                save_settings(cfg)
                self._json(_summary(cfg))
                return

            if path == '/api/preview':
                cfg = _config_from(payload.get('config') or {})
                src = payload.get('path') or ''
                if not os.path.isfile(src):
                    self._json(dict(ok=False, error='文件不存在：%s' % src))
                    return
                res = batch.make_one(src, cfg, write=False)
                self._json(dict(ok=True, result=res))
                return

            if path == '/api/hpc/bundle':
                cfg = _config_from(payload.get('config') or {})
                auto = not payload.get('paths')
                paths = _gjf_paths(cfg, payload.get('paths'))
                if auto:
                    paths = _filter_gjf(paths, payload.get('kind'))
                if not paths:
                    self._json(dict(ok=False, error='该类型下没有 .gjf 文件'))
                    return
                out = batch.out_dir_for(cfg)
                info = hpc.make_bundle(cfg, paths, out)
                self._json(dict(ok=True, bundle=info))
                return

            if path == '/api/hpc/logout':
                with HPC_LOCK:
                    cli = HPC_SESSION.get('cli')
                    if cli:
                        try:
                            cli.close()
                        except Exception:  # noqa: BLE001
                            pass
                    HPC_SESSION.update(cli=None, host='', user='', since=0.0)
                self._json(dict(ok=True, session=_hpc_session_info()))
                return

            if path in ('/api/hpc/login', '/api/hpc/submit', '/api/hpc/status',
                        '/api/hpc/fetch', '/api/hpc/chk', '/api/hpc/ls',
                        '/api/hpc/run', '/api/hpc/cancel'):
                cfg = _config_from(payload.get('config') or {})
                remote = (payload.get('remote_dir') or cfg.get('remote_dir') or '~/g16jobs').strip()
                if payload.get('host') and not cfg.get('hpc_host'):
                    cfg['hpc_host'] = payload['host']
                try:
                    cli, sess = _hpc_client(payload)
                    if path == '/api/hpc/login':
                        out, err, code = cli.run('hostname; whoami; pwd')
                        self._json(dict(ok=True, output=(out + err).strip(),
                                        session=_hpc_session_info()))
                        return
                    if path == '/api/hpc/status':
                        hist = cli.history()
                        self._json(dict(ok=True, squeue=cli.status(),
                                        history=hist.get('text', ''),
                                        history_available=bool(hist.get('available')),
                                        session=_hpc_session_info()))
                        return
                    if path == '/api/hpc/chk':
                        local = os.path.join(batch.out_dir_for(cfg), 'chk')
                        wanted = [n for n in (payload.get('names') or []) if n]
                        entries = cli.list_remote(remote, '.chk')
                        if wanted:
                            entries = [e for e in entries if e['name'] in wanted]
                        if not entries:
                            self._json(dict(ok=False, error='没有选中任何 .chk 文件'))
                            return
                        out_entries = []
                        for e in entries:
                            ok, msg, fchk_name, fchk_size = cli.run_formchk(remote, e['name'])
                            item = dict(name=e['name'], chk_size=e['size'],
                                        fchk=fchk_name, fchk_size=fchk_size,
                                        ok=ok, message=msg[-400:])
                            out_entries.append(item)
                        names = []
                        for e in out_entries:
                            names.append(e['name'])
                            if e['ok']:
                                names.append(e['fchk'])
                        files = cli.download_files(remote, names, local) if names else []
                        self._json(dict(ok=True, entries=out_entries, files=files,
                                        dir=local, session=_hpc_session_info()))
                        return

                    if path == '/api/hpc/run':
                        cmd = (payload.get('cmd') or '').strip()
                        res = cli.run_command(cmd, timeout=int(payload.get('timeout') or 300))
                        self._json(dict(ok=True, output=res['output'], code=res['code'],
                                        session=_hpc_session_info()))
                        return

                    if path == '/api/hpc/cancel':
                        ids = payload.get('ids') or []
                        res = cli.cancel_jobs(ids)
                        self._json(dict(ok=True, output=res['output'], code=res['code'],
                                        ids=res['ids'], squeue=cli.status(),
                                        session=_hpc_session_info()))
                        return

                    if path == '/api/hpc/ls':
                        suffix = (payload.get('suffix') or 'log').lower()
                        info = cli.list_files(remote)
                        allf = info['files']
                        if suffix == 'chk':
                            files = [f for f in allf
                                     if f['name'].lower().endswith('.chk')]
                            kind = 'chk'
                        else:
                            files = [f for f in allf
                                     if f['name'].lower().endswith(('.log', '.out', '.err'))]
                            kind = 'log'
                        self._json(dict(ok=True, files=files, dir=remote,
                                        root=info.get('root'), exists=info.get('exists'),
                                        total=len(allf), kind=kind,
                                        session=_hpc_session_info()))
                        return

                    if path == '/api/hpc/fetch':
                        local = os.path.join(batch.out_dir_for(cfg), 'logs')
                        names = [n for n in (payload.get('names') or []) if n]
                        if names:
                            files = cli.download_named(remote, names, local)
                        else:
                            files = cli.fetch_logs(remote, local)
                        self._json(dict(ok=True, files=files, dir=local,
                                        session=_hpc_session_info()))
                        return
                    # submit
                    auto = not payload.get('paths')
                    paths = _gjf_paths(cfg, payload.get('paths'))
                    if auto:
                        paths = _filter_gjf(paths, payload.get('kind'))
                    if not paths:
                        self._json(dict(ok=False, error='没有选中任何 .gjf 文件'))
                        return
                    info = hpc.make_bundle(cfg, paths, batch.out_dir_for(cfg))
                    cli.upload_dir(info['root'], remote)
                    # 先跑基态（含 _gs），再用 afterok 依赖提交 _td / _fc
                    names = info['names']
                    phase1 = [n for n in names if not _dep_base(n)]
                    phase2 = [n for n in names if _dep_base(n)]
                    ids = cli.submit(remote, phase1) if phase1 else {}
                    idmap = {n: (ids.get(n) or {}).get('jobid') for n in phase1}
                    deps = {}
                    for n in phase2:
                        base = _dep_base(n)
                        if idmap.get(base):
                            deps[n] = [idmap[base]]
                    if phase2:
                        ids.update(cli.submit(remote, phase2, deps=deps))
                    self._json(dict(ok=True, bundle=info['root'], remote=remote, jobs=ids,
                                    deps=deps, auto=auto, squeue=cli.status(),
                                    session=_hpc_session_info()))
                    return
                except Exception as exc:  # noqa: BLE001
                    self._json(dict(ok=False, error=str(exc),
                                    session=_hpc_session_info()), 500)
                    return

            if path == '/api/gjf/list':
                cfg = _config_from(payload.get('config') or {})
                od = (payload.get('dir') or batch.out_dir_for(cfg)).strip()
                files = []
                if os.path.isdir(od):
                    for fn in sorted(os.listdir(od)):
                        if not fn.lower().endswith('.gjf'):
                            continue
                        p2 = os.path.join(od, fn)
                        try:
                            st = os.stat(p2)
                        except OSError:
                            continue
                        files.append(dict(name=fn, path=p2, size=st.st_size,
                                          mtime=time.strftime(
                                              '%Y-%m-%d %H:%M',
                                              time.localtime(st.st_mtime))))
                files.sort(key=lambda f: f['mtime'], reverse=True)
                self._json(dict(ok=True, dir=od, files=files))
                return

            if path == '/api/logs/parse':
                folder = (payload.get('dir') or '').strip()
                if os.path.isfile(folder):
                    folder = os.path.dirname(folder)
                if not folder or not os.path.isdir(folder):
                    cfg2 = _config_from(payload.get('config') or {})
                    cand = os.path.join(batch.out_dir_for(cfg2), 'logs')
                    folder = cand if os.path.isdir(cand) else batch.out_dir_for(cfg2)
                if not os.path.isdir(folder):
                    self._json(dict(ok=False, error='目录不存在：%s' % folder))
                    return
                results = glog.parse_folder(folder)
                self._json(dict(ok=True, dir=folder, results=results,
                                summaries=[glog.summarize(r) for r in results]))
                return

            if path == '/api/make':
                cfg = _config_from(payload.get('config') or {})
                paths = payload.get('paths') or []
                paths = [p for p in paths if os.path.isfile(p)]
                if not paths:
                    self._json(dict(ok=False, error='没有选中任何文件'))
                    return
                results = batch.make_many(paths, cfg)
                save_settings(cfg)
                ok = sum(1 for r in results if not r.get('error'))
                self._json(dict(ok=True, results=results, n_ok=ok,
                                n_fail=len(results) - ok,
                                out_dir=batch.out_dir_for(cfg)))
                return

            self._json(dict(ok=False, error='未知接口：%s' % path), 404)
        except Exception as exc:  # noqa: BLE001
            self._error(exc)

    # ---------------------------------------------------------- 静态文件
    def _static(self, rel):
        rel = rel.split('?')[0]
        if rel in ('', '/'):
            rel = '/index.html'
        p = os.path.normpath(os.path.join(WEB_DIR, rel.lstrip('/')))
        if not p.startswith(WEB_DIR) or not os.path.isfile(p):
            self._send(404, b'not found', 'text/plain; charset=utf-8')
            return
        ctype = {'.html': 'text/html; charset=utf-8',
                 '.js': 'application/javascript; charset=utf-8',
                 '.css': 'text/css; charset=utf-8',
                 '.png': 'image/png', '.svg': 'image/svg+xml'}.get(
                     os.path.splitext(p)[1].lower(), 'application/octet-stream')
        with open(p, 'rb') as fh:
            self._send(200, fh.read(), ctype)


def _port_busy(port, host='127.0.0.1'):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


def _already_running(port):
    """这个端口上是不是已经跑着一个本工具。"""
    try:
        with urllib.request.urlopen('http://127.0.0.1:%d/api/state' % port,
                                    timeout=1.5) as r:
            data = json.loads(r.read().decode('utf-8', 'replace'))
        return bool(data.get('ok') and data.get('version'))
    except Exception:  # noqa: BLE001
        return False


def _free_port(preferred=8795):
    for port in range(preferred, preferred + 40):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    port = None
    no_browser = '--no-browser' in argv
    for i, a in enumerate(argv):
        if a == '--port' and i + 1 < len(argv):
            port = int(argv[i + 1])
    probe = port or 8795
    if _port_busy(probe) and _already_running(probe):
        url = 'http://127.0.0.1:%d/' % probe
        print('工具已经在运行：%s' % url)
        if not no_browser:
            threading.Timer(0.4, lambda: webbrowser.open(url)).start()
        return 0
    port = port or _free_port()
    srv = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    url = 'http://127.0.0.1:%d/' % port
    print('高斯计算工具已启动：%s' % url)
    print('（关闭这个窗口即可停止服务）')
    if not no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
