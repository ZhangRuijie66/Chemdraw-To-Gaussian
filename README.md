# 高斯计算工具 · ChemDraw → 3D → .gjf → 北大 HPC

把 ChemDraw 画的分子一键变成 Gaussian 输入文件（.gjf），并**直接提交到北大高性能计算平台**
（教学二号等），跑完还能把日志/结果读回来解析、画计算 UV-Vis 谱。

**不联网、不上传数据**：结构转换、3D 生成、结果解析全在本机完成；只有点「上传并提交」时才连集群。

当前版本：**v0.6.1**（2026-10-25）

---

## 快速开始

### 方式一：直接运行（Windows，推荐）

1. 从 GitHub 下载 ZIP（`Code` → `Download ZIP`），或使用发布页的便携版 zip，解压；
2. 双击解压目录**根部**的 **`启动.cmd`**：
   - 如果这个文件夹在作者的工作区里（上级有共享 `_tools\hidden-launch.vbs`），会无黑框启动；
   - 如果是单独下载的源码包，会自动改用本地启动器（会保留一个控制台窗口），
     首次运行自动安装 `rdkit` / `numpy` / `matplotlib` / `paramiko`（需要联网，走清华镜像）；
3. 浏览器自动打开 `http://127.0.0.1:8795/`；
4. 左侧选 ChemDraw 文件目录 → 「扫描」→ 勾选分子 → 「生成 .gjf」。

> ⚠️ 不要双击旧的 `_tools\hidden-launch.vbs` 快捷方式。新版源码包在该位置放了一个
> 兼容 shim，但它只负责转去根目录的 `启动.cmd`；最稳妥的是删除旧快捷方式，
> 以后直接双击根目录的 `启动.cmd`。
>
> 关闭那个黑色命令行窗口即停止服务；数据全程在本机。

### 方式二：源码运行（任意系统）

```bash
git clone git@github.com:ZhangRuijie66/Chemdraw-To-Gaussian.git
cd Chemdraw-To-Gaussian
python -m pip install -r requirements.txt
python run.py
```

命令行批量转换：

```bash
python run.py --test                          # 接口自检 + 扫默认目录生成到 _test_out
python run.py --make 输入目录 输出目录           # 批量生成 .gjf
python run.py --make 输入 输出 --functional B3LYP --basis 6-31G(d) --job opt
python make_portable.py                       # 打包便携版 zip（输出到 ../发布）
```

依赖：`rdkit`（结构/3D）、`numpy`+`matplotlib`（解析与作图）、`paramiko`（SSH 提交；
仓库不含 `vendor/`，需 pip 安装）。

---

## 它做什么

```
A1.cdxml / A1.cdx / A1.mol
        │  （.cdx 先用本机 ChemDraw 转成 molfile）
        ▼
   RDKit 读结构（键级、电荷、隐式氢、从 2D 坐标读双键顺反）
        │  ETKDG 生成 3D + MMFF94 力场优化（双键顺反照 ChemDraw 画法）
        │  [可选] 换成 Chem3D：ChemScript 转 3D + MM2，见「3D 后端」
        ▼
   .gjf（头部 + route + 标题 + 电荷/多重度 + 坐标 + 两个空行）
        │  + job_<名字>.sh / submit_all.sh / README.txt（提交包）
        ▼
   教学二号（Slurm/Crane）：sbatch → 排队 → 运行 g16
        │
        ▼
   下载 .log / .chk（自动 formchk 转 .fchk）→ 解析 → TD-DFT UV-Vis 图
```

生成的 .gjf 与课程模板 `calculation\A1-2.gjf` 逐字对齐（头部 8 行、坐标列宽
`%2s%28.8f%14.8f%14.8f`、CRLF 换行、末尾两个空行）。

---

## 网页界面（按栏说明）

### 输入 / 输出

- **ChemDraw 文件目录**：支持 `.cdxml / .cdx / .mol / .sdf`，点「扫描」列出分子；
- **输出目录**：留空 = `输入目录\gjf`；生成的文件不会覆盖 Chem3D 直接导出的原件。

### 计算设置

- 任务类型：`opt freq` / `opt` / `freq` / `TD-DFT 单点` / `opt + TD` / `振动分辨 (FC/HT)`；
- 泛函、基组、色散、溶剂、溶剂模型、核数、内存、TD 激发态数、构象数、力场、chk 后缀、尾部空行；
- **3D 后端**：RDKit（默认）/ Chem3D；选 Chem3D 时在「Chem3D Python」填 3.9/3.10 解释器路径
  （详见下面的「3D 后端」一节）；
- 「同时生成 TD-DFT 单点文件」= 一次生成 `X.gjf` + `X_td.gjf`（两步法）；
- 下方实时显示当前 route 行。

### 分子（勾选要生成的）

扫描后**默认全不选**，勾选后点蓝色「生成 .gjf」；点分子名可在底部预览区看全文。
覆盖同名文件时会先备份成 `<名字>.gjf.bak`。

### 超算提交（北大 HPC）

| 区块 | 说明 |
| --- | --- |
| 集群 | 教学二号 / 未名一号 / 未名二号 / 生科一号；选中后自动填分区、QOS、墙钟、地址 |
| **提交哪些分子** | 勾了就走快速通道；**一个都不勾** = 提交时再挑文件 |
| 提交类型 | 全部 / 优化频率 / TD 单点(_td) / 振动分辨第一步(_gs) / 第二步(_fc) / 单独频率(_freq) |
| 登录（保持连接） | 密码 + OTP 一次，之后所有操作复用这条 SSH 连接（服务端 30 s 心跳） |
| 上传并提交 | 先弹「选择要打包/提交的 .gjf」面板（文件名/大小/修改时间），确认后上传并 sbatch |
| 仅生成提交包 | 只生成本地 `hpc_<分子>_<类型>_<时间>/` + zip，不连集群（离线准备/发给同学/留档） |
| 查询作业 | `squeue` 排队/运行中，并显示每条作业的状态/理由（如 `DependencyNeverSatisfied`） |
| 读取日志 | 先列远程 `.log/.out/.err`（**带大小和最后修改时间**），勾选后再下载，自动解析 |
| 读取 chk | 列远程 `.chk`，勾选后在集群上 `formchk` 转 `.fchk`，再把 `.chk` + `.fchk` 下载到 `输出目录\chk\` |
| 命令行 | 在登录节点执行任意命令（`squeue -u $USER`、`sbatch job_A1.sh`、`ls -lh *.log`…），回车即执行，输出进控制台 |
| 取消作业 | 填作业号（空格分隔）→ `scancel`，并回显当前队列 |
| 清空输出 | 清掉控制台缓冲 |

**作业依赖**：一次提交里同时有基态和 `_td`（或 `_gs` + `_fc`）时，工具先提交基态，拿到 job id 后
用 `sbatch --dependency=afterok:<id>` 提交依赖作业；脚本里还有兜底（基态 chk 不存在 / 日志没有
`Normal termination` 就直接退出）。

### 生成结果 / 计算结果 / 预览

- **生成结果**：每个分子生成了哪些文件、原子数、MMFF 能量、route；
- **计算结果**：解析日志得到状态（正常/错误终止及 link）、SCF 能量、是否优化收敛、虚频数、
  TD-DFT 的 S1 与**最强吸收跃迁**（f≈0 的标「暗」）；
- 结果表里点「UV-Vis 图」→ 画该分子的计算谱（0.3 eV 高斯展宽），同时存 `<名字>_uvvis.png`；
- 底部 **预览**：点左侧分子名查看生成的 .gjf 全文。

---

## 命令行（CLI）

```bat
python run.py --test                     :: 接口自检 + 扫 calculation 目录生成到 _test_out
python run.py --make 输入目录 输出目录    :: 批量转换
python run.py --make 输入 输出 --functional B3LYP --basis 6-31G(d) --job opt
python run.py --port 8795 --no-browser   :: 指定端口 / 不自动开浏览器
python make_portable.py [输出目录]        :: 打包便携版
```

`--test` 会先检查 `HpcClient` 的方法是否齐全，能挡住"改代码时误删方法"这类问题。

---

## 泛函 / 基组 / 方法目录

### 泛函（Gaussian 关键词）

| 关键词 | 名称 | 适用 |
| --- | --- | --- |
| `B3LYP` | B3LYP | 最常用；基态几何、振动频率 |
| `PBE1PBE` | PBE0 | 几何与激发能略优于 B3LYP（模板用它） |
| `M062X` | M06-2X | 主族热化学、激发能（自带色散） |
| `wB97XD` | ωB97X-D | 长程校正 + 自带色散；CT 态 |
| `CAM-B3LYP` | CAM-B3LYP | 长程校正；CT/Rydberg、花青染料可作对照 |
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
| `freq` | 只算频率（`geom=check`，读已有 chk） |
| `TD=(NStates=10,Singlets)` | TD-DFT 单点激发能（`geom=check guess=read`） |
| `opt freq` + `TD` | 同一任务里优化后算激发态 |
| `Freq=(ReadFC,FC,HT) TD=(…,Read)` | 振动分辨（FC/HT），需先有 `freq=(SaveNormalModes)` 的 chk |

### 常用附加关键词

- 色散：`EmpiricalDispersion=GD3BJ`（Becke–Johnson 阻尼）/ `GD3`（零阻尼）；
  M06-2X、ωB97X-D 自带色散，不用再加。
- 积分格点：`Int=(UltraFine,NoXCTest)`；SCF 加速：`SCF=NoVarAcc`（G16 C.01+）。
- 隐式溶剂：`SCRF=(IEFPCM,Solvent=Ethanol)` 或 `SCRF=(SMD,Solvent=Ethanol)`。
- 大基组/激发态可加 `SCF=(XQC)`；开壳层用 `UKS` 或改多重度。

---

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

TD 单点文件：

```
%oldchk=A1_opt.chk
%chk=A1_td.chk
%nprocshared=32
%mem=160GB
#p PBE1PBE/def2TZVP TD(NStates=10, Singlet) Geom=Check Guess=Read

TD-DFT UV-Vis calculation at PBE0/def2-TZVP level

1 1
```

---

## 双键顺反（E/Z）

ChemDraw 的 **2D 坐标里带着每个双键的顺反信息**，工具会把它读出来，3D 起始结构
**照抄 ChemDraw 的画法**：画成顺式就是顺式，画成反式就是反式；图上没体现顺反的
双键（如画成直线、取代基对称）由 ETKDG 按固定随机种子决定，结果可复现。

> 历史上曾默认把所有非环 C=C 强制成反式（E），2026-10-29 起已移除该逻辑：
> 需要全反式构象时，请在 ChemDraw 里把双键画成反式即可。

---

## 3D 后端：RDKit（默认）/ Chem3D

2D → 3D 这一步有两个可切换的后端，在「计算设置 → 3D 后端」里选：

| 后端 | 怎么做 3D | 依赖 | 适用 |
| --- | --- | --- | --- |
| **RDKit（默认）** | ETKDG 嵌入 + MMFF94 力场优化（顺反照 ChemDraw 画法） | `rdkit`（工具自带） | 日常使用；MMFF94 对 S/N 的参数更靠谱 |
| Chem3D | ChemScript：`ReadFile → ConvertTo3DStructure → 循环 MM2` | Python **3.9 / 3.10** + 本机 ChemOffice；在「Chem3D Python」填解释器路径（或设环境变量 `CHEM3D_PYTHON`） | 想复现课上的 Chem3D/MM2 流程，或要更平的共轭链 |

要点：

- **为什么用子进程**：主程序跑在 Python 3.11，而 ChemScript 只有 `_ChemScriptForPy39.pyd` /
  `_ChemScriptForPy310.pyd`，3.11 里 import 必失败。所以 Chem3D 后端由 `gcalc/chem3d.py`
  起一个 3.10 子进程跑 `gcalc/chem3d_worker.py`，用 JSON 传回原子/键/电荷/分子式/MM2 能量，
  **主程序不用换解释器**。
- **ChemScript 不认中文路径**（中文路径下 `ReadFile` 静默失败、不抛异常）：工具会自动把输入
  复制到 `C:\Temp\chem3dwork\` 再读。找不到解释器 / 跑失败时，「生成结果」里会给出明确原因，
  按提示在设置里填 3.10 的 `python.exe` 即可。
- **MM2 的两个已知偏差**：C–S 键被压到约 1.47 Å（A2 文献约 1.73 Å；MMFF94 给 1.79），
  而且共轭多烯会被**强制拉成全反式**（2-丁烯的顺式能保留，己三烯/四烯/A2 的顺式会被翻掉）。
  RDKit 后端已移除强制反式（2026-10-29），顺反照 ChemDraw 画法；要精确保留手绘的顺式
  共轭链，请用默认的 RDKit 后端，Chem3D 后端只适合全反式体系；两种后端都只是起始结构，
  最终几何靠 Gaussian 的 `opt`。
- TD-DFT / 单独 freq 不需要 3D 坐标：即使选了 Chem3D，也只做 RDKit 解析，不启动 ChemScript。
- 如果系统的 `PYTHONPATH` 里同时有 `C:\Program Files (x86)\...\ChemScript\Lib`（32 位）和
  64 位的那份，worker 会先把指定的 Lib 提到最前，避免 64 位 Python 误加载 32 位 `.pyd`。

本机示例：

```text
Chem3D Python：...\python310\cpython-3.10.20-windows-x86_64-none\python.exe   （uv 装的独立 3.10）
ChemScript Lib：C:\Program Files\PerkinElmerInformatics\ChemOffice\ChemScript\Lib
```

---

## 超算提交（北大 HPC · Slurm）

平台规则（据 <https://hpc.pku.edu.cn/ug/guide/access/> 与 /ug/soft/gaussian/）：

| 项目 | 说明 |
| --- | --- |
| 登录方式 | SSH，**密码 + OTP 动态码**（Keyboard Interactive）；**不支持密钥登录** |
| 登录环境 | 必须在校园网内；登录节点不能联网，只用来提交 |
| 集群地址 | 未名一号 `wm1-login.pku.edu.cn`、未名二号 `wm2-login.pku.edu.cn`、生科一号 `wmsk1-login`、教学二号 `wmjx2-login` |
| 调度器 | Slurm 系（教学二号是 Crane 前端）：`sbatch` / `squeue` / `scancel` / `sacct` |
| 分区 | 教学二号用 `compute`；查询分区/内存用 `sinfo -o "%P %m %c"` |
| Gaussian | 不是 module：用户自己装在 `$HOME`，需 `export g16root=$HOME; export GAUSS_SCRDIR=$HOME/tmp; source $g16root/g16/bsd/g16.profile` |
| 墙钟 | 教学二号最长 **2 天**（默认 `2-00:00:00`）；未名一号/生科一号最长 5 天 |
| 特例 | 教学二号提交命令是 `g16 < x.gjf`，且**没有 `$SLURM_SUBMIT_DIR`**（脚本里不要 cd 到它） |

工具里做的事：

1. **生成提交包**（不需要登录）：每个分子一个 `job_<名字>.sh` + `submit_all.sh` + README.txt，
   连同 `.gjf` 打包成 `hpc_<分子>_<类型>_<时间>/`（含 zip）。默认按教学二号的写法：
   `#SBATCH -p compute`、`g16 < x.gjf > x.log`。
2. **登录一次、保持连接**：点「登录（保持连接）」输一次密码 + OTP，之后「上传并提交 / 查询作业 /
   读取日志 / 读取 chk / 命令行 / 取消作业」都复用这条 SSH 连接（服务端每 30 s 心跳），
   **不用重复输 OTP**；点「断开」或连接超时才需要重新登录。密码和 OTP 只在内存里用，不写磁盘。
3. **结果读回**：下载日志后自动解析 `.log`，列出状态（正常/错误终止及哪个 link）、SCF 能量、
   是否优化收敛、虚频数、TD-DFT 第一激发态与最强跃迁；`.chk` 可在集群上 `formchk` 转 `.fchk`
   再下载（GaussView / Multiwfn 可读）。

> ⚠️ OTP 是「每次**新连接**一次性」的；只要这条连接不断就不再要。会话存在服务进程里，
> **重启工具会丢会话**，需要重新登录（集群上的作业不受影响）。

---

## chk → fchk

点「读取 chk」→ 列出远程 `.chk`（名字/大小/修改时间）→ 勾选 →「转换并下载选中」：

1. 在集群登录节点执行 `formchk <名字>.chk <名字>.fchk`（找不到时自动用 `$HOME/g16/formchk`）；
2. 把 `.chk` 和 `.fchk` 一起下载到 `输出目录\chk\`；
3. 控制台逐条显示 `✓ A1_opt.chk (112 MB) → A1_opt.fchk (… MB)`，失败会带 formchk 的报错。

`.chk` 是二进制，只有 Gaussian 系程序能直接读；`.fchk` 是文本，GaussView、Avogadro、Multiwfn 都能打开。

---

## 计算 UV-Vis 谱

TD-DFT 结果表里点「UV-Vis 图」：

- 棒状谱（每个允许跃迁按振子强度 f 画竖线）+ 0.3 eV 高斯展宽的包络；
- 自动标注最强跃迁（态号、波长、f）；
- 保存为日志旁边的 `<名字>_uvvis.png`。

> 高对称分子（如苯）的 S1 可能对称性禁阻（f=0），此时应看「最强吸收跃迁」而不是 S1。
> TD-DFT 对花青类染料会系统性高估能隙（链越长越明显，可达 0.5–0.6 eV），这是方法本身的
> 局限；需要更准的值可换长程校正泛函（CAM-B3LYP / ωB97X-D）或 RI-CC2 对照。

---

## 振动分辨的 UV-Vis（Franck-Condon / Herzberg-Teller）

Gaussian 16 Rev C.01 起支持 FC/HT 振动分辨电子谱。任务类型选「振动分辨 (FC/HT)」会生成两个文件：

1. `<分子>_gs.gjf` —— 基态 `opt freq=(SaveNormalModes)`，把简正模存进 chk；
2. `<分子>_fc.gjf` —— `%oldchk=<分子>_gs.chk` +
   `#p Freq=(ReadFC,FC,HT) TD=(NStates=10, Singlet, Read) …/… Geom=Check Guess=Read`。

先跑 gs、再跑 fc。代价：FC/HT 要算激发态 Hessian（数值），约 3N 次 TD 计算；
苯（12 原子）几十分钟到一两小时，A1/A2（42/46 原子）贵一个量级。

目前只生成输入，还没解析 Gaussian 打印的 vibronic 谱带表。

---

## 已知限制

- **.cdx** 依赖本机安装的 ChemDraw（通过 COM 转 molfile）；`.cdxml` / `.mol` 不需要。
- 3D 结构来自 RDKit 力场 + 「全反式」约束，是 Gaussian `opt` 的**起始结构**，不是最终构型。
- Chem3D 后端要另装 Python 3.9/3.10 + 本机 ChemOffice；MM2 的 C–S 偏短约 0.26 Å，且会把
  共轭多烯强制成全反式（顺式异构体只能靠 RDKit 后端）；每次预览/生成都会起一次 3.10 子进程
  （A2 约 2 秒，B1 约 2.3 秒，含解释器与 ChemScript 启动）。
- 电荷/多重度：电荷自动取自 ChemDraw 结构；多重度默认 1（单重态），开壳层需手动改。
- **`opt freq` 对 90+ 原子的大分子很吃内存**：β-胡萝卜素（96 原子）的 freq 在 L1101 阶段
  被 OOM 杀掉过；报告只比 λmax 的话做 `opt` 就够，确实要 freq 建议把 `%mem` 降到 32–64 GB
  或换小基组。
- 振动分辨（FC/HT）只生成输入，尚未解析输出。
- 日志/chk 重复下载会覆盖本地同名文件（`.gjf` 有 `.bak`，日志没有）。
- 会话存在服务进程里，**重启工具就要重新输 OTP**（平台不支持密钥登录）。
- 「查询作业」对教学二号的 `squeue` 做了多种写法兜底，全失败时会打印每条命令的返回。

---

## 目录结构

```
高斯计算工具/
  run.py              入口（网页 / --test / --make）
  make_portable.py    打包便携版
  gcalc/
    methods.py        泛函、基组、任务目录 + route 拼装
    cdxml.py          CDXML 解析（含 2D 顺反）、.cdx → mol（ChemDraw COM）
    embed.py          RDKit 3D 嵌入 + MMFF94 + 全反式约束
    chem3d.py         可选 3D 后端（Chem3D）：起 3.10 子进程调 ChemScript
    chem3d_worker.py  ChemScript worker（必须 3.9/3.10）：cdxml → 3D → 循环 MM2 → JSON
    gjf.py            .gjf 格式（照 A1-2.gjf 逐字对齐）
    batch.py          扫描目录、批量生成
    hpc.py            SSH 连接、提交包、sbatch 依赖、squeue/scancel、formchk、下载
    glog.py           Gaussian 日志解析
    plotting.py       TD-DFT UV-Vis 作图
    server.py         本地网页服务（127.0.0.1）
  web/                前端页面
  docs/               使用说明（便携版）
  tools/              便携版启动器
  vendor/             内置 paramiko（不进仓库）
  settings.json       本机设置（不进仓库）
  启动.cmd            双击启动
```

---

## 更新日志

| 版本 | 日期 | 主要变化 |
| --- | --- | --- |
| v0.6.1 | 2026-10-25 | 修复：源码 ZIP 的启动器依赖作者工作区的共享 `_tools`；新增本地回退与 `_tools` 兼容 shim |
| 2026-10-23 | 新增 | 3D 后端可选 **Chem3D**（ChemScript + MM2，3.10 子进程）；默认仍 RDKit，顺反控制不变 |
| v0.6.0 | 2026-10-23 | 新增「命令行」执行任意远程命令、「取消作业」(scancel) |
| 2026-10-23 | 修复 | ChemDraw 双键顺反丢失导致长链分子被建成顺式；非环 C=C 默认全反式 |
| v0.5.x | 2026-10-22 | 提交类型与分子筛选、提交前文件选择面板、日志先读取（带修改时间）再勾选下载、chk 读取与 formchk 转 fchk、孤立 TD/freq 不再覆盖基态 chk、日志解析容错 |
| v0.4.x | 2026-10-22 | 提交包按「分子+类型+时间」命名、作业 afterok 依赖、修 chk 覆盖问题 |
| v0.3.x | 2026-10-21 | UV-Vis 作图、结果解析表格、两步 TD |
