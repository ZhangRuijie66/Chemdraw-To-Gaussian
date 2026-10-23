# -*- coding: utf-8 -*-
"""北大高性能计算平台（Slurm）的提交接口。

平台要点（https://hpc.pku.edu.cn/ug/guide/access/ 与 /ug/soft/gaussian/）：
  · 只能 SSH 登录，密码 + OTP 动态码（Keyboard Interactive），**不支持密钥登录**；
    登录必须在校园网内。
  · 登录节点不能联网、只用于提交；数据传输节点可联网、可访问存储。
  · 调度器 Slurm：sbatch / squeue / scancel / sacct。
  · Gaussian 不是 module，而是用户自己装在 $HOME（g16root=$HOME、
    GAUSS_SCRDIR=$HOME/tmp、source $g16root/g16/bsd/g16.profile）。
  · 未名教学二号用 `g16 < x.gjf`（重定向）而不是 `g16 x.gjf`。
"""
from __future__ import annotations

import os
import shutil
import time

CLUSTERS = [
    # key, 名称, 登录节点, 数据传输节点, 说明
    ('wm1', '未名一号', 'wm1-login.pku.edu.cn', 'wm1-data.pku.edu.cn', '最常见的分区 C032M0128G'),
    ('wm2', '未名二号', 'wm2-login.pku.edu.cn', 'wm2-data.pku.edu.cn', '单节点多核要用 --ntasks'),
    ('sk1', '生科一号', 'wmsk1-login.pku.edu.cn', '', '生命科学相关'),
    ('jx2', '教学二号', 'wmjx2-login.pku.edu.cn', '', '提交命令是 g16 < x.gjf'),
]

DEFAULT_PARTITION = 'C032M0128G'
DEFAULT_QOS = 'low'

# 每个集群的默认提交参数（用户 2026-10-21 给的 g16sub.sh 是教学二号的写法）
CLUSTER_DEFAULTS = {
    'jx2': dict(partition='compute', qos='', redirect=True, env=False,
                walltime='2-00:00:00', cd_submit_dir=False),
    'wm1': dict(partition='C032M0128G', qos='low', redirect=False, env=True),
    'wm2': dict(partition='C032M0128G', qos='low', redirect=False, env=True),
    'sk1': dict(partition='C032M0128G', qos='low', redirect=False, env=True),
}


def cluster_defaults(key):
    """集群的默认提交参数（分区/QOS/墙钟），给网页切换集群时自动填。"""
    c = cluster_info(key)
    d = dict(CLUSTER_DEFAULTS.get(c['key'], CLUSTER_DEFAULTS['wm1']))
    return dict(partition=d.get('partition', DEFAULT_PARTITION),
                qos=d.get('qos', ''),
                walltime=d.get('walltime', '5-00:00:00'),
                redirect=d.get('redirect', False),
                include_env=d.get('env', True))


def cluster_info(key):
    for c in CLUSTERS:
        if c[0] == key:
            return dict(key=c[0], name=c[1], login=c[2], data=c[3], note=c[4])
    return dict(key='wm1', name='未名一号', login='wm1-login.pku.edu.cn',
                data='wm1-data.pku.edu.cn', note='')


def _gaussian_env_lines(cfg):
    lines = []
    g16root = (cfg.get('g16root') or '$HOME').strip() or '$HOME'
    scrdir = (cfg.get('scr_dir') or '$HOME/tmp').strip() or '$HOME/tmp'
    lines.append('export g16root=%s' % g16root)
    lines.append('export GAUSS_SCRDIR=%s' % scrdir)
    lines.append('source $g16root/g16/bsd/g16.profile')
    return lines


def build_slurm_script(cfg, name, gjf_name=None):
    """单个 .gjf 的 Slurm 作业脚本。"""
    gjf_name = gjf_name or (name + '.gjf')
    cluster_key = cfg.get('cluster') or 'jx2'
    cluster = cluster_info(cluster_key)
    cdef = CLUSTER_DEFAULTS.get(cluster['key'], CLUSTER_DEFAULTS['wm1'])
    partition = (cfg.get('partition') or cdef['partition']).strip()
    qos = (cfg.get('qos') if cfg.get('qos') is not None else cdef['qos'])
    qos = (qos or '').strip()
    redirect = bool(cfg.get('redirect', cdef['redirect']))
    include_env = bool(cfg.get('include_env', cdef['env']))
    nodes = int(cfg.get('nodes') or 1)
    ntasks = int(cfg.get('ntasks') or 32)
    walltime = (cfg.get('walltime') if cfg.get('walltime') is not None else
                cdef.get('walltime', '5-00:00:00')).strip()
    tag = (cfg.get('job_tag') or '').strip()
    job_name = (tag + '-' + name) if tag else name
    job_name = job_name[:60]

    outpat = (cfg.get('sbatch_out') or 'job.%j.out').strip()
    L = ['#!/bin/bash',
         '#SBATCH -o %s' % outpat,
         '#SBATCH -p %s' % partition,
         ]
    if qos:
        L.append('#SBATCH --qos=%s' % qos)
    L += ['#SBATCH -J %s' % job_name,
         '#SBATCH -N %d' % nodes]
    if cluster['key'] == 'wm2':
        # 未名二号：单节点多核用 --ntasks（平台文档明确说明）
        L.append('#SBATCH --ntasks=%d' % ntasks)
    else:
        L.append('#SBATCH --ntasks-per-node=%d' % ntasks)
    L.append('#SBATCH --get-user-env')
    if walltime:
        L.append('#SBATCH -t %s' % walltime)
    L.append('')
    if include_env:
        L += _gaussian_env_lines(cfg)
        L.append('')
    if cdef.get('cd_submit_dir', True):
        L.append('cd $SLURM_SUBMIT_DIR')
    # 依赖作业的兜底检查：基态 chk 不在 / 日志不是正常结束，就直接退出
    low = name.lower()
    if low.endswith('_td'):
        base = name[:-3]
        L.append('[ -f %s_opt.chk ] || { echo "缺少 %s_opt.chk，基态还没算完？"; exit 1; }'
                 % (base, base))
        L.append('grep -q "Normal termination" %s.log 2>/dev/null || '
                 '{ echo "%s.log 不是正常结束，取消 TD"; exit 1; }' % (base, base))
    elif low.endswith('_fc'):
        base = name[:-3] + '_gs'
        L.append('[ -f %s.chk ] || { echo "缺少 %s.chk，基态还没算完？"; exit 1; }'
                 % (base, base))
        L.append('grep -q "Normal termination" %s.log 2>/dev/null || '
                 '{ echo "%s.log 不是正常结束，取消 FC"; exit 1; }' % (base, base))
    if redirect:
        L.append('g16 < %s > %s.log 2>&1' % (gjf_name, name))
    else:
        L.append('g16 %s > %s.log 2>&1' % (gjf_name, name))
    L.append('')
    return '\n'.join(L)


def _dep_base_name(name):
    low = name.lower()
    if low.endswith('_td'):
        return name[:-3]
    if low.endswith('_fc'):
        return name[:-3] + '_gs'
    return None


def build_submit_all(names):
    """生成 submit_all.sh：先提交基态，再用 afterok 依赖提交 _td / _fc。"""
    bases = [n for n in names if not _dep_base_name(n)]
    deps = [n for n in names if _dep_base_name(n)]
    L = ['#!/bin/bash',
         '# 依次提交：先基态，再按 afterok 依赖提交 TD / FC',
         'cd "$(dirname "$0")"',
         'jid() { grep -o "[0-9][0-9]*" | head -n1; }',
         '']
    for n in bases:
        L.append('J_%s=$(sbatch job_%s.sh | jid); echo "%s -> $J_%s"'
                 % (n.replace('-', '_'), n, n, n.replace('-', '_')))
    if deps:
        L.append('')
    for n in deps:
        b = _dep_base_name(n)
        key = n.replace('-', '_')
        if b in bases:
            bkey = b.replace('-', '_')
            L.append('J_%s=$(sbatch --dependency=afterok:$J_%s job_%s.sh | jid); '
                     'echo "%s (afterok $J_%s) -> $J_%s"' % (key, bkey, n, n, bkey, key))
        else:
            L.append('sbatch job_%s.sh   # 依赖的基态不在这批里，需自行确认 chk 已存在' % n)
    return chr(10).join(L) + chr(10)


def build_readme(cfg, names):
    cluster = cluster_info(cfg.get('cluster') or 'wm1')
    remote = cfg.get('remote_dir') or '~/g16jobs'
    lines = [
        '高斯作业提交包',
        '=' * 40,
        '集群：%s（%s）' % (cluster['name'], cluster['login']),
        '远程目录：%s' % remote,
        '',
        '一、上传（任选其一）',
        '  1) Xftp / FileZilla / WinSCP：连到 %s（或数据传输节点 %s），' % (cluster['login'], cluster['data'] or cluster['login']),
        '     把整个文件夹传到 %s；' % remote,
        '  2) 可视化平台 SCOW：文件管理 → 上传；',
        '  3) 本工具的「上传并提交」按钮（需要密码 + OTP）。',
        '',
        '二、登录（校园网内，密码 + 手机 OTP）',
        '  ssh 学号@%s' % cluster['login'],
        '',
        '三、提交',
        '  cd %s' % remote,
        '  bash submit_all.sh          # 全部提交',
        '  # 或单个：sbatch job_%s.sh' % (names[0] if names else 'A1'),
        '',
        '四、查看状态 / 结果',
        '  squeue -u $USER             # 排队/运行中',
        '  sacct -j <jobid> --format=JobID,State,Elapsed,MaxRSS',
        '  ls *.log                    # Gaussian 输出',
        '',
        '五、Gaussian 环境（脚本里已写好，按需改）',
        '  export g16root=$HOME',
        '  export GAUSS_SCRDIR=$HOME/tmp',
        '  source $g16root/g16/bsd/g16.profile',
        '',
        '注意：登录节点不能联网；模板里 %nprocshared 要和 --ntasks-per-node 一致。',
    ]
    return '\n'.join(lines) + '\n'


_KIND_SUFFIX = (('_td', 'td'), ('_freq', 'freq'), ('_gs', 'gs'), ('_fc', 'fc'))


def bundle_label(names):
    """给提交包起个能看懂的名字：分子 + 计算类型。"""
    mols, kinds = [], []
    for n in names:
        tag = 'opt'
        base = n
        for suf, t in _KIND_SUFFIX:
            if base.lower().endswith(suf):
                tag = t
                base = base[:-len(suf)]
                break
        if base not in mols:
            mols.append(base)
        if tag not in kinds:
            kinds.append(tag)
    mol_txt = '-'.join(mols[:3])
    if len(mols) > 3:
        mol_txt += '等%d个' % len(mols)
    return '%s_%s' % (mol_txt, '-'.join(kinds))


def make_bundle(cfg, gjf_paths, out_dir):
    """把 .gjf + 作业脚本 + 说明 打包到一个文件夹（可选 zip）。"""
    ts = time.strftime('%Y%m%d-%H%M%S')
    label = (cfg.get('bundle_label') or bundle_label(
        [os.path.splitext(os.path.basename(p))[0] for p in gjf_paths]))
    root = os.path.join(out_dir, 'hpc_%s_%s' % (label, ts))
    n = 1
    while os.path.exists(root):
        root = os.path.join(out_dir, 'hpc_%s_%s_%d' % (label, ts, n))
        n += 1
    os.makedirs(root)
    names = []
    for src in gjf_paths:
        base = os.path.splitext(os.path.basename(src))[0]
        names.append(base)
        shutil.copyfile(src, os.path.join(root, base + '.gjf'))
        script = build_slurm_script(cfg, base)
        with open(os.path.join(root, 'job_%s.sh' % base), 'w', encoding='utf-8',
                  newline='\n') as fh:
            fh.write(script)
    with open(os.path.join(root, 'submit_all.sh'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(build_submit_all(names))
    with open(os.path.join(root, 'README.txt'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(build_readme(cfg, names))
    # 只保留最近 10 个 hpc_* 打包目录，避免越积越多
    try:
        olds = sorted([d for d in os.listdir(out_dir) if d.startswith('hpc_')],
                      reverse=True)
        for d in olds[10:]:
            shutil.rmtree(os.path.join(out_dir, d), ignore_errors=True)
            zp = os.path.join(out_dir, d + '.zip')
            if os.path.exists(zp):
                os.remove(zp)
    except OSError:
        pass

    zip_path = ''
    if cfg.get('make_zip'):
        zip_path = shutil.make_archive(root, 'zip', root)
    return dict(root=root, zip=zip_path, names=names, label=label,
                scripts={n: build_slurm_script(cfg, n) for n in names},
                readme=build_readme(cfg, names))


# ---------------------------------------------------------------- SSH
def _load_paramiko():
    import sys
    vendor = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'vendor')
    if os.path.isdir(vendor) and vendor not in sys.path:
        sys.path.insert(0, vendor)
    import paramiko  # noqa: F401
    return paramiko


class HpcError(RuntimeError):
    pass


class HpcClient:
    """密码 + OTP 的 SSH/SFTP 客户端（凭据只在内存里，不落盘）。"""

    def __init__(self, host, user, password, otp, port=22, timeout=25):
        self.host = host
        self.user = user
        self.password = password
        self.otp = otp or ''
        self.port = int(port or 22)
        self.timeout = timeout
        self.client = None

    def connect(self):
        paramiko = _load_paramiko()
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            cli.connect(self.host, port=self.port, username=self.user,
                        password=self.password, timeout=self.timeout,
                        allow_agent=False, look_for_keys=False,
                        banner_timeout=self.timeout, auth_timeout=self.timeout)
            try:
                cli.get_transport().set_keepalive(30)
            except Exception:  # noqa: BLE001
                pass
            self.client = cli
            return self
        except Exception as first:  # noqa: BLE001
            # 服务器要求 Keyboard Interactive（密码 + OTP）
            try:
                self._connect_interactive(paramiko, cli)
                self.client = cli
                try:
                    self.client.get_transport().set_keepalive(30)
                except Exception:  # noqa: BLE001
                    pass
                return self
            except Exception as second:  # noqa: BLE001
                raise HpcError('SSH 登录失败：%s / %s' % (first, second))

    def _connect_interactive(self, paramiko, cli):
        transport = paramiko.Transport((self.host, self.port))
        transport.banner_timeout = self.timeout
        transport.start_client(timeout=self.timeout)

        def handler(title, instructions, prompt_list):
            answers = []
            for prompt in prompt_list:
                p = (prompt[0] or '').lower()
                if 'verification' in p or 'otp' in p or 'code' in p or '令牌' in p:
                    answers.append(self.otp)
                elif 'password' in p or '密码' in p:
                    answers.append(self.password)
                else:
                    answers.append(self.otp or self.password)
            return answers

        transport.auth_interactive(self.user, handler)
        if not transport.is_authenticated():
            raise HpcError('Keyboard Interactive 认证未通过（密码或 OTP 不对？）')
        cli._transport = transport
        self.client = cli

    # ---------------------------------------------------------- 操作
    def _sftp(self):
        return self.client.open_sftp()

    def resolve_remote(self, remote_dir):
        """把 ~/xxx 展开成绝对路径（SFTP 不认 ~）。"""
        rd = (remote_dir or '').strip()
        if not rd.startswith('~'):
            return rd
        out, err, code = self.run('cd %s 2>/dev/null && pwd' % rd)
        if code == 0 and out.strip():
            return out.strip().splitlines()[-1]
        out, err, code = self.run('echo $HOME')
        home = out.strip().splitlines()[-1] if out.strip() else ''
        return (home + rd[1:]) if home else rd

    def mkdir_p(self, remote_dir):
        sftp = self._sftp()
        path = ''
        for part in remote_dir.replace('\\', '/').split('/'):
            if not part:
                path = '/'
                continue
            path = path.rstrip('/') + '/' + part
            try:
                sftp.stat(path)
            except IOError:
                sftp.mkdir(path)
        sftp.close()

    def upload_dir(self, local_dir, remote_dir):
        remote_dir = self.resolve_remote(remote_dir)
        self.mkdir_p(remote_dir)
        sftp = self._sftp()
        for fn in os.listdir(local_dir):
            local = os.path.join(local_dir, fn)
            if os.path.isfile(local):
                sftp.put(local, remote_dir.rstrip('/') + '/' + fn)
        sftp.close()

    def run(self, cmd, timeout=60):
        if self.client is None:
            raise HpcError('SSH 连接未建立（请重新登录）')
        stdin, stdout, stderr = self.client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode('utf-8', 'replace')
        err = stderr.read().decode('utf-8', 'replace')
        code = stdout.channel.recv_exit_status()
        return out, err, code

    def run_command(self, cmd, timeout=300):
        """在登录节点执行一条命令（远程 shell），返回输出和退出码。"""
        cmd = (cmd or '').strip()
        if not cmd:
            raise HpcError('命令为空')
        out, err, code = self.run(cmd, timeout=timeout)
        return dict(output=((out or '') + (err or '')).strip(), code=code)

    def cancel_jobs(self, ids):
        """scancel 指定作业号。"""
        ids = [str(i).strip() for i in (ids or []) if str(i).strip()]
        if not ids:
            raise HpcError('没有作业号')
        out, err, code = self.run('scancel ' + ' '.join(ids))
        return dict(output=((out or '') + (err or '')).strip(), code=code, ids=ids)

    def submit(self, remote_dir, names, deps=None):
        """提交作业；deps = {作业名: [前置 job id]} → sbatch --dependency=afterok:…"""
        remote_dir = self.resolve_remote(remote_dir)
        ids = {}
        deps = deps or {}
        listing = ''
        try:
            out, err, code = self.run('ls -la %s' % remote_dir)
            listing = (out + err).strip()
        except Exception:  # noqa: BLE001
            pass
        for n in names:
            dep = [d for d in (deps.get(n) or []) if d]
            depflag = ('--dependency=afterok:%s ' % ','.join(dep)) if dep else ''
            cmd = 'cd %s && sbatch %sjob_%s.sh' % (remote_dir, depflag, n)
            out, err, code = self.run(cmd)
            text = (out + err).strip()
            jobid = ''
            import re as _re
            m = _re.search(r'(\d{3,})', text)
            if m:
                jobid = m.group(1)
            ids[n] = dict(jobid=jobid, output=text, ok=(code == 0))
        if ids:
            for k in ids:
                ids[k]['listing'] = listing
        return ids

    def status(self):
        """依次尝试几种 squeue 写法，返回第一个能正常出结果的。

        教学二号是 Crane 调度，squeue 带 -o "%i …" 会报 invalid format specifier，
        所以这里带降级尝试和诊断信息。
        """
        cands = [
            'squeue -u %s' % self.user,
            'squeue --user=%s' % self.user,
            'squeue -u %s -o "%%A %%j %%T %%M %%R"' % self.user,
            'squeue',
            'scontrol show jobs 2>/dev/null | head -60',
        ]
        tried = []
        for cmd in cands:
            try:
                out, err, code = self.run(cmd, timeout=30)
            except Exception as exc:  # noqa: BLE001
                tried.append((cmd, 'EXC %s' % exc))
                continue
            text = (out or '').strip()
            errtext = (err or '').strip()
            if text and not errtext:
                return text
            tried.append((cmd, errtext or text or '(空输出)'))
        return '查询失败，试过的命令：' + ''.join(
            '\n  $ %s  ->  %s' % (c, r) for c, r in tried)

    def history(self):
        """近两天已完成作业。返回 dict(available, text)。

        教学二号没有 Slurm 的 sacct（Crane 调度），所以先探测命令是否存在，
        不存在就不要在界面上显示一栏空白。
        """
        probe, _, _ = self.run('command -v sacct 2>/dev/null')
        if not (probe or '').strip():
            return dict(available=False, text='')
        out, err, code = self.run(
            'sacct -u %s -S $(date -d "-2 days" +%%Y-%%m-%%d) '
            '--format=JobID,JobName%%20,State,Elapsed,MaxRSS -n '
            '2>/dev/null || true' % self.user)
        return dict(available=True, text=(out or '').strip())

    def list_files(self, remote_dir, depth=2):
        """用 SFTP 列远程文件（名字含相对路径 / 字节数 / 修改时间），最多下探 depth 层。

        不依赖远程 shell 的 find/ls 参数差异；返回 dict(files, exists)，
        exists=False 表示目录本身不存在。
        """
        rd = self.resolve_remote(remote_dir)
        sftp = self._sftp()
        files = []
        state = dict(exists=False)

        def walk(path, prefix, level):
            try:
                attrs = sftp.listdir_attr(path)
            except IOError:
                return
            if level == 1:
                state['exists'] = True
            for a in attrs:
                name = a.filename
                if not name or name.startswith('.'):
                    continue
                full = path.rstrip('/') + '/' + name
                rel = prefix + name
                is_dir = bool((a.st_mode or 0) & 0o040000)
                if is_dir:
                    if level < depth:
                        walk(full, rel + '/', level + 1)
                else:
                    files.append(dict(
                        name=rel,
                        size=int(a.st_size or 0),
                        mtime=time.strftime('%Y-%m-%d %H:%M',
                                            time.localtime(a.st_mtime or 0))))

        try:
            walk(rd, '', 1)
        finally:
            sftp.close()
        files.sort(key=lambda f: f['mtime'], reverse=True)
        return dict(files=files, exists=state['exists'], root=rd)

    def list_remote(self, remote_dir, suffix='.chk'):
        """列出远程目录里某类文件及大小（含子目录，名字是相对路径）。"""
        info = self.list_files(remote_dir)
        entries = [dict(name=f['name'], size=f['size'], mtime=f['mtime'])
                   for f in info['files'] if f['name'].lower().endswith(suffix)]
        return entries

    def run_formchk(self, remote_dir, chk_name):
        """远程把 .chk 转成 .fchk（Gaussian 的 formchk）；返回 (ok, 输出, fchk名, 大小)。"""
        rd = self.resolve_remote(remote_dir)
        fchk = (chk_name[:-4] + '.fchk' if chk_name.lower().endswith('.chk')
                else chk_name + '.fchk')
        cmd = ('cd %s && rm -f %s && (formchk %s %s 2>&1 || '
               '$HOME/g16/formchk %s %s 2>&1)'
               % (rd, fchk, chk_name, fchk, chk_name, fchk))
        out, err, code = self.run(cmd, timeout=600)
        text = ((out or '') + (err or '')).strip()
        fchk_size = 0
        try:
            s2, e2, c2 = self.run('cd %s && stat -c %%s %s 2>/dev/null' % (rd, fchk))
            fchk_size = int((s2 or '').strip() or 0)
        except Exception:  # noqa: BLE001
            pass
        return (code == 0 and fchk_size > 0), text, fchk, fchk_size

    def download_files(self, remote_dir, names, local_dir):
        """按文件名下载（.chk / .fchk 用）。"""
        rd = self.resolve_remote(remote_dir)
        os.makedirs(local_dir, exist_ok=True)
        sftp = self._sftp()
        got = []
        try:
            for fn in names:
                rel = fn.replace(chr(92), '/').lstrip('/')
                local = os.path.join(local_dir, os.path.basename(rel))
                sftp.get(rd.rstrip('/') + '/' + rel, local)
                got.append(local)
        finally:
            sftp.close()
        return got

    def download_named(self, remote_dir, names, local_dir):
        """按文件名下载（日志用）。"""
        return self.download_files(remote_dir, names, local_dir)

    def fetch_logs(self, remote_dir, local_dir):
        remote_dir = self.resolve_remote(remote_dir)
        os.makedirs(local_dir, exist_ok=True)
        sftp = self._sftp()
        got = []
        try:
            for attr in sftp.listdir_attr(remote_dir):
                if attr.filename.lower().endswith(('.log', '.out', '.err')):
                    remote = remote_dir.rstrip('/') + '/' + attr.filename
                    local = os.path.join(local_dir, attr.filename)
                    sftp.get(remote, local)
                    got.append(local)
        finally:
            sftp.close()
        return got

    def is_alive(self):
        try:
            tr = self.client.get_transport() if self.client else None
            return bool(tr and tr.is_active())
        except Exception:  # noqa: BLE001
            return False

    def close(self):
        try:
            if self.client:
                self.client.close()
        except Exception:  # noqa: BLE001
            pass
