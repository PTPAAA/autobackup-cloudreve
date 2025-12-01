# CloudBackup

本项目为**开源、轻量级**的自动化备份解决方案，基于 Python 开发。它遵循 **3-2-1 备份原则**，集成了本地高压缩归档、完整性校验以及可选的 [Cloudreve](https://github.com/cloudreve/Cloudreve) 私有云同步功能。

- **核心理念**：数据无价，校验先行。
- **主要功能**：本地镜像 -> 7-Zip 高压 -> 哈希校验 -> 云端同步。
- **适用场景**：服务器数据冷备、NAS 文件上云、个人重要资料归档。

## 安装与依赖

本项目依赖 Python 3 环境及 7-Zip 压缩软件。

### 1. 安装系统依赖 (7-Zip)

- **Windows**: 下载并安装 [7-Zip](https://www.7-zip.org/) (默认路径 `C:\Program Files\7-Zip\7z.exe` 即可自动识别)。
- **Linux (Debian/Ubuntu)**:
  ```bash
  apt-get update && apt-get install p7zip-full
  ```
- **macOS**:
  ```bash
  brew install p7zip
  ```

### 2. 安装 Python 依赖

```bash
pip3 install tqdm schedule cloudreve
```
*(注：如果不使用云同步功能，可不安装 `cloudreve` 库，脚本会自动降级为仅本地备份模式)*

## 功能特性

| 功能模块 | 特性描述 | 状态 |
| :--- | :--- | :--- |
| **核心架构** | 3段式流水线 (复制-压缩-校验) | ✅ |
| **智能分卷** | <1GB 单文件 / ≥1GB 自动分卷 (默认1GB/卷) | ✅ |
| **数据校验** | 7-Zip 原生 `t` 指令哈希校验，确保 0% 损坏 | ✅ |
| **任务调度** | 内置守护线程，支持每日定时自动执行 | ✅ |
| **多云同步** | 支持同时上传至多个 Cloudreve 节点 | ✅ |
| **断点续传** | 网络波动自动重试，文件冲突智能跳过 | ✅ |
| **开发者工具** | 内置压力测试 (Test Mode) 与垃圾清理 | ✅ |

## 快速开始

### 1. 首次运行配置

直接运行脚本，首次启动会自动进入向导模式：

```bash
python main.py
```

根据提示输入：
- **源目录**: 你要备份的文件夹路径。
- **备份仓**: 存放压缩包的本地路径。
- **Cloudreve 配置**: (可选) 配置你的私有云地址、账号、密码及远程存储目录。

### 2. 常用指令

脚本启动后提供交互式命令行，支持以下指令：

```bash
指令 > backup    # 立即执行一次完整备份 (含上传)
指令 > test      # 压力测试模式 (生成随机数据验证流程)
指令 > deltest   # 一键清理测试产生的 _TEST 临时文件
指令 > setup     # 重新运行配置向导
指令 > cloudreve # 管理云端账号 (添加/删除)
指令 > exit      # 退出程序
```

### 3. 后台挂机

配置完成后，保持脚本运行即可。它会在每天设定的时间（默认 `03:00`）自动执行备份任务。

推荐使用 `screen` 或 `nohup` 在后台运行：
```bash
nohup python main.py >/dev/null 2>&1 &
```

## 开发者工具 (Dev Tools)

为了验证备份系统的稳定性，本项目内置了压力测试模块。

- **`test` 指令**：
  你可以指定生成例如 `5GB` 的随机二进制垃圾数据，脚本将模拟完整的 **镜像 -> 压缩 -> 校验** 流程。
  *注：测试生成的备份文件夹会自动标记 `_TEST` 后缀，不会污染正式数据，且默认不会上传到云端。*

- **`deltest` 指令**：
  一键扫描并删除备份仓库中所有带 `_TEST` 后缀的测试残留目录，快速释放磁盘空间。

## 目录结构说明

备份完成后，你的本地仓库将呈现以下结构：

```text
/Backup_Root
├── 23.11.30/                 # 日期目录
│   ├── source_120000.7z      # 小文件：直接归档
│   └── source_Split_120000/  # 大文件：分卷目录
│       ├── source.7z.001
│       ├── source.7z.002
│       └── ...
└── config.json               # 配置文件
```

## 感谢

- [Cloudreve](https://github.com/cloudreve/Cloudreve): 优秀的公私兼备网盘系统。
- [cloudreve-sdk](https://github.com/yxzlwz/cloudreve-sdk): 本项目使用的 Python SDK。
- [7-Zip](https://www.7-zip.org/): 高压缩率的归档工具。

## License

MIT License
