# 高斯计算工具（第一步：ChemDraw → 3D → .gjf）

把 ChemDraw 画的分子一键变成可以直接上传超算的 Gaussian 输入文件。
**不联网、不上传数据**，所有转换都在本机完成。

## 快速开始

### 方式一：便携版（推荐，Windows 直接用）

1. 下载本仓库（`Code` → `Download ZIP`），解压；
2. 双击 **`启动.cmd`**，首次运行会自动安装依赖
   （`rdkit` / `numpy` / `matplotlib` / `paramiko`，走清华镜像，需要联网）；
3. 浏览器自动打开 `http://127.0.0.1:8795/`；
4. 左侧选 ChemDraw 文件目录 → 「扫描」→ 勾选分子 → 「生成 .gjf」。

> 关闭那个黑色命令行窗口即停止服务；数据全程在本机，不上传。

### 方式二：源码运行（任意系统）

```bash
git clone git@github.com:ZhangRuijie66/Chemdraw-To-Gaussian.git
cd Chemdraw-To-Gaussian
python -m pip install -r requirements.txt
python run.py
```

也可以在命令行批量转换：

```bash
python run.py --test                          # 自检
python run.py --make 输入目录 输出目录           # 批量生成 .gjf
```

依赖说明：`rdkit`（结构/3D）、`numpy`+`matplotlib`（解析与作图）、`paramiko`（SSH 提交，
仓库不含 `vendor/`，需 pip 安装）。

## 它做什么

```
A1.cdxml / A1.cdx / A1.mol
        │  （.cdx 先用本机 ChemDraw 转成 molfile）
        ▼
     RDKit 读结构（键级、电荷、隐式氢）
        │  ETKDG 生成 3D 构象 + MMFF94 力场优化（多构象取能量最低）
        ▼
   .gjf（头部 + route + 标题 + 电荷/多重度 + 坐标 + 两个空行）
```

生成的文件格式与 `calculation\A1-2.gjf` 逐字对齐（头部 8 行、坐标列宽、
`%2s%28.8f%14.8f%14.8f`、CRLF 换行、末尾两个空行）。

## 网页界面

双击 `启动.cmd`（或 `python run.py`），浏览器会自动打开。

1. **输入目录**：选放 ChemDraw 文件的文件夹（支持 `.cdxml`、`.cdx`、`.mol`、`.sdf`），点「扫描」；
2. **计算设置**：任务类型、泛函、基组、色散、溶剂、核数/内存、TD 激发态数、构象数、
   力场、尾部空行数；route 行会实时显示；
3. **勾选分子** → 点右上角「生成 .gjf」；
4. 默认输出到 `输入目录\gjf\`（不会覆盖 Chem3D 直接导出的 `A1.gjf`），
   点左侧分子名可以在右边预览生成的文本。

## 命令行

```bat
python run.py --test                     :: 自检：扫 calculation 目录，生成到 _test_out
python run.py --make 输入目录 输出目录    :: 批量转换
python run.py --make 输入 输出 --functional B3LYP --basis 6-31G(d) --job opt
```

## 泛函 / 基组 / 方法目录

### 泛函（Gaussian 关键词）

| 关键词 | 名称 | 适用 |
| --- | --- | --- |
| `B3LYP` | B3LYP | 最常用；基态几何、振动频率 |
| `PBE1PBE` | PBE0 | 几何与激发能略优于 B3LYP（模板用它） |
| `M062X` | M06-2X | 主族热化学、激发能（自带色散） |
| `wB97XD` | ωB97X-D | 长程校正 + 自带色散；CT 态 |
| `CAM-B3LYP` | CAM-B3LYP | 长程校正；CT/Rydberg |
| `B3PW91` | B3PW91 | 与 B3LYP 相近 |
| `TPSSTPSS` | TPSSh | 过渡金属、弱相互作用 |
| `B3LYP5` | B3LYP(5) | 复现老文献的 B3LYP 定义 |
| `HF` | HF | 参考 |

### 基组

| 关键词 | 说明 |
| --- | --- |
| `6-31G(d)` | 双 ζ + d 极化，几何优化性价比最高 |
| `6-31+G(d,p)` | 加弥散；阴离子、弱相互作用 |
| `6-311G(d,p)` / `6-311+G(d,p)` | 三 ζ + 极化 |
| `def2SVP` / `def2TZVP` / `def2TZVPP` | Ahlrichs 系列，重元素自带 ECP（模板用 def2TZVP） |
| `cc-pVDZ` / `cc-pVTZ` / `aug-cc-pVTZ` | 相关一致基组 |
| `LANL2DZ` / `SDD` | 赝势，过渡金属/重元素 |

### 任务类型

| 关键词 | 用法 |
| --- | --- |
| `opt freq` | 优化 + 频率（默认） |
| `opt` | 只优化 |
| `freq` | 只算频率（`geom=check`） |
| `TD=(NStates=10,Singlets)` | TD-DFT 单点激发能（`geom=check guess=read`） |
| `opt freq` + `TD` | 同一任务里优化后算激发态 |

### 常用附加关键词

- 色散：`EmpiricalDispersion=GD3BJ`（Becke–Johnson 阻尼）/ `GD3`（零阻尼）；
  M06-2X、ωB97X-D 自带色散，不用再加。
- 积分格点：`Int=(UltraFine,NoXCTest)`；SCF 加速：`SCF=NoVarAcc`（G16 C.01+）。
- 隐式溶剂：`SCRF=(IEFPCM,Solvent=Ethanol)` 或 `SCRF=(SMD,Solvent=Ethanol)`。
- 大基组/激发态可加 `SCF=(XQC)`；开壳层用 `UKS` 或改多重度。

## 生成的 .gjf 长什么样

```
%nprocshared=32
%mem=160GB
%chk=A1_opt.chk
#p opt freq PBE1PBE/def2TZVP EmpiricalDispersion=GD3BJ Int=(UltraFine,NoXCTest) SCF=NoVarAcc

A1

1 1
 C                  5.12904922   -2.09350382    1.05686136
 ...

```
（坐标块后留**两个空行**；可用「尾部空行」调成 1~4 个。）

## 已知限制

- **.cdx** 依赖本机安装的 ChemDraw（通过 COM 转 molfile）；`.cdxml`/`.mol` 不需要。
- 3D 结构来自 RDKit 力场，是 Gaussian `opt` 的**起始结构**，不是最终构型；
  柔性链（乙基）可能有多个构象，可把「构象数」调大取能量最低者。
- 电荷/多重度：电荷自动取自 ChemDraw 结构；多重度默认 1（单重态），开壳层需手动改。
- 两步法（`opt` → `TD`）的 `_td.gjf` 用 `geom=check guess=read`，**必须先跑完 opt 的 chk**。

## 目录结构

```
高斯计算工具/
  run.py              入口（网页 / --test / --make）
  gcalc/
    methods.py        泛函、基组、任务目录 + route 拼装
    cdxml.py          CDXML 解析、.cdx → mol（ChemDraw COM）
    embed.py          RDKit 3D 嵌入 + MMFF94
    gjf.py            .gjf 格式（照 A1-2.gjf 逐字对齐）
    batch.py          扫描目录、批量生成
    server.py         本地网页服务
  web/                前端页面
  settings.json       默认设置
  启动.cmd            双击启动
```


## 超算提交（北大 HPC · Slurm）

平台规则（据 <https://hpc.pku.edu.cn/ug/guide/access/> 与 /ug/soft/gaussian/）：

| 项目 | 说明 |
| --- | --- |
| 登录方式 | SSH，**密码 + OTP 动态码**（Keyboard Interactive）；**不支持密钥登录** |
| 登录环境 | 必须在校园网内；登录节点不能联网，只用来提交；数据传输节点可联网 |
| 集群地址 | 未名一号 `wm1-login.pku.edu.cn`（数据节点 `wm1-data.pku.edu.cn`）、未名二号 `wm2-login.pku.edu.cn`（`wm2-data`）、生科一号 `wmsk1-login`、教学二号 `wmjx2-login` |
| 调度器 | Slurm：`sbatch` / `squeue` / `scancel` / `sacct` |
| 分区 | 例：未名一号 `C032M0128G`（32 核 / 124 G），用 `sinfo -o "%P %m %c"` 查 |
| Gaussian | 不是 module：用户自己装在 `$HOME`，需 `export g16root=$HOME; export GAUSS_SCRDIR=$HOME/tmp; source $g16root/g16/bsd/g16.profile` |
| 墙钟 | 教学二号最长 **2 天**（默认 `2-00:00:00`）；未名一号/生科一号最长 5 天 |
| 特例 | 未名二号单节点多核要用 `--ntasks`（平台 bug）；教学二号提交命令是 `g16 < x.gjf` |

工具里做了三件事：

1. **生成提交包**（不需要登录）：每个分子一个 `job_<名字>.sh` + `submit_all.sh` + README，
   连同 `.gjf` 打包成 zip。上传到集群后 `bash submit_all.sh` 即可。
   默认按教学二号的写法（用户 2026-10-21 的 `g16sub.sh`）：
   `#SBATCH -p compute`、无 qos、`g16 < x.gjf > x.log`。
2. **登录一次、保持连接**：点「登录（保持连接）」输一次密码 + OTP，之后
   「上传并提交 / 查询作业 / 下载日志」都复用这条 SSH 连接（服务端每 30 s 发心跳），
   **不用重复输 OTP**；点「断开」或连接超时才需要重新登录。
   密码和 OTP 只在内存里用，不写磁盘；OTP 用一次即作废，登录成功后输入框自动清空。
3. **结果读回**：下载日志后自动解析 `.log`，列出每个分子的
   状态（正常/错误终止及哪个 link）、SCF 能量、是否优化收敛、虚频数、TD-DFT 第一激发态
   （eV / nm / 振子强度 f）。错误终止会显示如 `l502.exe`（SCF 不收敛）。

> ⚠️ 平台不支持密钥登录，OTP 是「每次**新连接**一次性」的；只要这条连接不断，
> 就不再要 OTP。所以别频繁点「断开」，也别重启工具（会话在服务进程里）。


## 振动分辨的 UV-Vis（Franck-Condon / Herzberg-Teller）

Gaussian 16 Rev C.01 起支持 FC/HT 振动分辨电子谱。工具里新增任务类型「振动分辨 (FC/HT)」，
会给每个分子生成两个文件：

1. `<分子>_gs.gjf` —— 基态 `opt freq=(SaveNormalModes)`，把简正模存进 chk；
2. `<分子>_fc.gjf` —— `%oldchk=<分子>_gs.chk` +
   `#p Freq=(ReadFC,FC,HT) TD=(NStates=10, Singlet, Read) …/… Geom=Check Guess=Read`。

先跑 gs（拿到 `<分子>_gs.chk`），**再**跑 fc。代价：FC/HT 要算激发态 Hessian（数值），
约 3N 次 TD 计算；苯（12 原子）几十分钟到一两小时，A1/A2（42/46 原子）要贵一个量级。

输出里 Gaussian 会打印振动分辨的谱带数据（0-0 带、Franck-Condon 包络）；
目前工具还没有解析这张表，等跑过一次再补解析和作图。


## 提交类型与作业依赖（v0.4.1）

- 「超算提交」里新增**提交类型**：全部 / 优化频率 / TD 单点（_td）/ 振动分辨第一步（_gs）/
  第二步（_fc）。选择任务类型时会自动切到对应的提交类型。
- **保证顺序**：一次提交里如果同时有基态和 `_td`（或 `_gs` 和 `_fc`），工具会先提交基态、
  拿到 job id，再用 `sbatch --dependency=afterok:<id>` 提交依赖作业，基态没正常结束就不会启动。
- 脚本里还有一道兜底：`_td`/`_fc` 作业启动前检查基态 chk 是否存在、基态 `.log` 是否有
  `Normal termination`，不满足就打印原因并退出（防止 Gaussian 出错但 g16 仍返回 0 的情况）。
- 分两次提交或手动上传时没有依赖关系，需要自己加：
  `sbatch --dependency=afterok:<基态 jobid> job_A1_td.sh`
