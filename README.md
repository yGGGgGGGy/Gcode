# Gcode — 麒麟OS 智能运维Agent

**用自然语言管理系统，像聊天一样运维。**

在企业级数据中心环境中，运维人员常需处理复杂的系统问题，传统运维依赖脚本和监控，门槛高、效率低。Gcode 是一套部署于麒麟操作系统的智能运维 Agent，作为自然语言与 OS 交互的桥梁——你说"帮我查下磁盘"，它自动执行 `df -h` 并解释结果。

---

## 目录

- [核心能力](#核心能力)
- [系统架构](#系统架构)
- [环境要求](#环境要求)
- [新手一键部署](#新手一键部署)
- [配置 LLM 模型](#配置-llm-模型)
- [使用方法](#使用方法)
- [MCP Tool 列表](#mcp-tool-列表)
- [安全护栏机制](#安全护栏机制)
- [项目结构](#项目结构)
- [API 协议](#api-协议)
- [常见问题](#常见问题)

---

## 核心能力

| 能力 | 说明 |
|------|------|
| 自然语言运维 | 用中文描述需求，Agent 自动执行系统操作 |
| 三层安全护栏 | 意图过滤 + 最小权限 + 思维链审计，杜绝误操作 |
| 多模型切换 | 支持 Qwen / DeepSeek / Claude / Ollama 任意切换 |
| 麒麟OS 原生适配 | rpm/dnf、systemd、SELinux、auditd 全面兼容 |
| 全链路审计 | 每条操作都有记录，可回溯完整决策过程 |

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Gcode Agent                                │
│                                                                      │
│   用户: "帮我看下磁盘空间"                                              │
│         │                                                            │
│         ▼                                                            │
│   ┌──────────────────────────────────────┐                          │
│   │  🛡  Security Guard (安全层)          │                          │
│   │                                      │                          │
│   │  api/server.py      Unix Socket 入口  │                          │
│   │         │                            │                          │
│   │         ▼                            │                          │
│   │  intent/classifier.py   意图过滤器     │                          │
│   │  ├─ Qwen2.5-0.5B 零样本分类          │                          │
│   │  ├─ safe → 放行                      │                          │
│   │  ├─ unsafe → 拦截                    │                          │
│   │  └─ needs-review → 需人工确认          │                          │
│   │         │                            │                          │
│   │         ▼                            │                          │
│   │  reasoning/reasoner.py   推理层       │                          │
│   │  选择一个 LLM 决定调哪个 Tool           │                          │
│   │         │                            │                          │
│   └─────────┼────────────────────────────┘                          │
│             │  Unix Domain Socket                                     │
│             ▼                                                        │
│   ┌──────────────────────────────────────┐                          │
│   │  🔧 MCP Server (执行层)               │                          │
│   │                                      │                          │
│   │  server.py     FastMCP 协议入口       │                          │
│   │         │                            │                          │
│   │         ├─ tools_readonly.py   只读感知 │                          │
│   │         ├─ tools_metrics.py    指标采集 │                          │
│   │         └─ tools_management.py 管理执行 │                          │
│   │                   │                  │                          │
│   │                   ▼                  │                          │
│   │  executor.py    命令执行器            │                          │
│   │  ├─ 高危命令正则拦截                   │                          │
│   │  ├─ 敏感路径检测                      │                          │
│   │  ├─ dry-run 预览确认                  │                          │
│   │  └─ 实际执行                          │                          │
│   │                   │                  │                          │
│   │  sandbox.py     seccomp 沙箱          │                          │
│   │  ├─ 36 个系统调用白名单                │                          │
│   │  ├─ 512MB 内存限制                    │                          │
│   │  └─ 30s CPU 时间限制                 │                          │
│   └──────────────────────────────────────┘                          │
│             │                                                        │
│             ▼                                                        │
│   ┌──────────────────────────────────────┐                          │
│   │  📊 Audit (审计层)                    │                          │
│   │  └─ audit/logger.py   SQLite 全量记录 │                          │
│   └──────────────────────────────────────┘                          │
│             │                                                        │
└─────────────┼────────────────────────────────────────────────────────┘
              ▼
        麒麟OS (systemd / rpm / journalctl / ...)
```

### 数据流

```
用户输入 "重启 nginx"
  → api/server.py (接入)
  → intent/classifier.py (意图判定: safe)
  → reasoning/reasoner.py (LLM 决策: 调用 service_restart)
  → mcp/server.py (MCP 协议接收)
  → executor.py (参数校验 + dry-run)
  → sandbox.py (seccomp 沙箱执行)
  → audit/logger.py (记录审计日志)
  → 返回结果给用户
```

---

## 环境要求

| 项目 | 最低要求 | 推荐 |
|------|---------|------|
| **操作系统** | 麒麟OS V10 (Kylin Linux Advanced Server) | V10 SP3+ |
| **内核** | Linux 4.19+ | 5.10+ |
| **Python** | 3.11+ | 3.12 |
| **内存** | 4GB | 8GB+ |
| **磁盘** | 2GB 可用空间 | 5GB+ |
| **网络** | 可访问 LLM API 或本地运行 Ollama |
| **权限** | root（仅安装时），运行时用 gcode 用户 |

### 前置依赖

```bash
# Python 3.11+
python3 --version

# pip
python3 -m pip --version

# systemd (自带)
systemctl --version

# 安装 systemd 相关包 (麒麟默认已装)
sudo dnf install -y python3-devel gcc
```

---

## 新手一键部署

**步骤 1：安装前置依赖**

```bash
# 麒麟OS / CentOS / RHEL
sudo dnf install -y python3 python3-pip python3-devel gcc git

# Debian / Ubuntu
sudo apt install -y python3 python3-pip python3-venv python3-dev gcc git
```

**步骤 2：克隆项目**

```bash
git clone https://github.com/yGGGgGGGy/Gcode.git
cd Gcode
```

**步骤 3：一键安装**

```bash
# 自动完成: 创建用户 → 安装依赖 → 复制文件 → 设置权限 → 安装 systemd → 启动服务
sudo bash deploy/setup.sh
```

安装完成你会看到：

```
=== 部署完成 ===
服务状态:
● gcode-security-guard - active (running)
● gcode-mcp-server - active (running)
```

**步骤 4：验证安装**

```bash
# 查看服务状态
systemctl status gcode-security-guard gcode-mcp-server

# 发送测试请求
echo '{"query":"查看系统信息","user_id":"test"}' | socat - UNIX-CONNECT:/run/gcode/gcode.sock
```

### 手动部署（如果一键脚本失败）

```bash
# 1. 创建用户
sudo useradd -r -s /sbin/nologin -d /opt/gcode gcode

# 2. 创建目录
sudo mkdir -p /opt/gcode /run/gcode /opt/gcode/data/{audit,logs}

# 3. 安装 Python 依赖
cd /opt/gcode
sudo python3 -m venv .venv
sudo .venv/bin/pip install -e .

# 4. 复制代码
sudo cp -r . /opt/gcode/

# 5. 设置权限
sudo chown -R gcode:gcode /opt/gcode /run/gcode

# 6. 安装并启动服务
sudo cp deploy/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gcode-security-guard gcode-mcp-server
```

---

## 配置 LLM 模型

Gcode 支持多种大模型，在 `.env` 文件中配置：

```bash
# 复制配置模板
cp deploy/.env.template .env

# 编辑配置
vim .env
```

### 方案 A：本地 Ollama（免费，无需联网）

```bash
# 安装 Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# 下载模型
ollama pull qwen2.5:7b

# 在 .env 中设置
GCODE_LLM_PROVIDER=ollama
GCODE_OLLAMA_URL=http://localhost:11434
GCODE_OLLAMA_MODEL=qwen2.5:7b
```

### 方案 B：阿里云 Qwen API（国内推荐）

```bash
# .env
GCODE_LLM_PROVIDER=qwen
GCODE_QWEN_API_KEY=sk-your-key-here
GCODE_QWEN_MODEL=qwen-turbo
```

### 方案 C：DeepSeek API

```bash
# .env
GCODE_LLM_PROVIDER=deepseek
GCODE_DEEPSEEK_API_KEY=sk-your-key-here
GCODE_DEEPSEEK_MODEL=deepseek-chat
```

### 方案 D：Claude API

```bash
# .env
GCODE_LLM_PROVIDER=claude
GCODE_CLAUDE_API_KEY=sk-ant-your-key-here
GCODE_CLAUDE_MODEL=claude-sonnet-4-20250514
```

### 安装对应依赖

```bash
# 根据你选的 provider 安装
pip install ".[reasoner-openai]"     # Qwen / DeepSeek
pip install ".[reasoner-anthropic]"  # Claude
pip install ".[reasoner]"            # 全部
```

---

## 使用方法

安装完成后，直接用 `gcode` 命令：

```bash
gcode
```

进入交互模式：

```
  ╔══════════════════════════════════╗
  ║      Gcode 智能运维Agent        ║
  ║   用自然语言管理麒麟OS服务器      ║
  ╚══════════════════════════════════╝

  输入问题开始，例如:
    · 查看磁盘空间
    · CPU 使用率多少
    · nginx 服务状态怎么样

  输入 quit 或 Ctrl+C 退出
```

然后直接打中文就行，例如：

```
>> 查看磁盘空间
Filesystem  Size  Used Avail Use% Mounted on
/dev/sda1   50G   20G   28G  42% /

>> CPU 使用率多少
{'percent': 3.2, 'per_cpu': [2.1, 4.5, 3.0, 3.3], 'count': 4}

>> 重启 nginx
[预览]
nginx.service - nginx HTTP server
   Active: active (running)
[需要确认才能执行]

>> 帮我看看 /var/log/messages 最近10条日志
May  1 10:23:45 kylin kernel: ...
```

### 单次查询模式

```bash
# 直接带问题执行，不用进入交互
gcode 查看磁盘空间
gcode nginx 服务状态
gcode 帮我看看内存使用
```

### 开发模式

```bash
make test      # 运行测试
make run-guard # 启动安全层（单独调试）
make run-mcp   # 启动执行层（单独调试）
```

---

## MCP Tool 列表

### 只读感知（风险: read_only，直接执行）

| Tool | 说明 | 示例 |
|------|------|------|
| `sys_info` | 系统信息：内核版本、架构、麒麟版本 | `"查看系统信息"` |
| `ps_list` | 进程列表 | `"在跑哪些进程"` |
| `df_h` | 磁盘使用 | `"磁盘还有多少空间"` |
| `netstat` | 网络连接 | `"查看端口监听情况"` |
| `journalctl` | 系统日志 | `"nginx 最近50条日志"` |

### 指标采集（风险: read_only，直接执行）

| Tool | 说明 | 示例 |
|------|------|------|
| `cpu_usage` | CPU 使用率（总体 + 每核） | `"CPU 占用多少"` |
| `mem_usage` | 内存 + Swap 使用 | `"内存还剩多少"` |
| `io_stat` | 磁盘 IO 统计 | `"磁盘读写频繁吗"` |
| `disk_health` | 磁盘健康检查 | `"/data 分区健康吗"` |

### 管理执行（风险: admin，需确认）

| Tool | 说明 | 示例 |
|------|------|------|
| `service_status` | 服务状态（无需确认） | `"nginx 服务状态"` |
| `service_restart` | 重启服务（需确认） | `"重启 nginx"` |
| `pkg_install` | 安装 RPM 包（需确认） | `"装一个 nginx"` |

---

## 安全护栏机制

Gcode 的核心挑战在于解决 AI 推理的不可控性。我们设计了 **三层安全护栏** 来杜绝误操作：

### 第 1 层：意图风险过滤（入口）

作用于用户输入阶段，在 LLM 推理之前拦截。

- **快路径**：正则表达式匹配高危命令（`rm -rf`、`mkfs`、`dd`、`chmod 777`），命中直接返回 BLOCKED
- **慢路径**：Qwen2.5-0.5B 本地小模型做 13 标签零样本分类
- **判定结果**：
  - `safe` → 放行进入推理层
  - `unsafe` → 直接拒绝
  - `needs-review` → 拒绝，建议人工审核

### 第 2 层：最小权限执行（出口）

作用于 Tool 调用阶段，在执行前二次校验。

- **参数校验**：拒绝路径穿越（`../../../etc/passwd`）、命令注入字符（`;`、`&`）
- **dry-run 确认**：高风险操作先预览结果，返回给用户确认后才执行
- **seccomp 沙箱**：仅开放 36 个安全系统调用
- **资源限制**：512MB 内存上限、30s CPU 时间、64 个文件描述符
- **用户隔离**：以 `gcode` 用户运行，非 root

### 第 3 层：思维链审计（全链路）

作用于全流程，提供事后追溯能力。

- **全量记录**：用户输入 → 意图分析 → LLM 推理 → Tool 调用 → 执行结果
- **DAG 结构**：`session_id → step_id → parent_step_id` 链式追踪
- **异常检测规则**：
  - 同一 session 内先只读后管理操作 → 标记复核
  - 短时间内 3 个以上高危操作 → 触发熔断
  - 触碰敏感路径（`/etc/shadow`、`/root/.ssh`）→ 告警

---

## 项目结构

```
Gcode/
├── deploy/                          # 🚀 部署文件
│   ├── setup.sh                     #   一键部署脚本
│   ├── .env.template                #   配置文件模板
│   ├── gcode-security-guard.service #   安全层 systemd 单元
│   └── gcode-mcp-server.service     #   执行层 systemd 单元
├── schema/
│   └── gcode-protocol.json          #   m1↔dp1 完整协议定义
├── src/
│   ├── contracts/                   #   m1↔dp1 接口契约
│   │   └── types.py                 #   SessionContext, ToolCallRecord, ToolResult
│   ├── api/                         #   接入层
│   │   └── server.py                #   Unix Socket 服务器
│   ├── intent/                      #   意图过滤器
│   │   ├── classifier.py            #   Qwen2.5-0.5B 分类器
│   │   └── model.py                 #   标签体系 + INTENT_MAPPING
│   ├── audit/                       #   审计系统
│   │   ├── logger.py                #   SQLite 全量记录
│   │   └── models.py                #   审计数据模型
│   └── gcode/                       #   主业务模块
│       ├── mcp/                     #   🔧 MCP Server (dp1)
│       │   ├── server.py            #   FastMCP 协议入口
│       │   ├── executor.py          #   命令执行器 + 权限门禁
│       │   ├── sandbox.py           #   seccomp 沙箱 + 资源限制
│       │   ├── tools_readonly.py    #   只读感知 Tool (5个)
│       │   ├── tools_metrics.py     #   指标采集 Tool (4个)
│       │   └── tools_management.py  #   管理执行 Tool (3个)
│       ├── reasoning/               #   🧠 推理层 (多模型 LLM)
│       │   ├── reasoner.py          #   LLM 推理 + Tool 选择
│       │   ├── tool_registry.py     #   Tool 注册表
│       │   ├── providers/           #   LLM 适配器
│       │   │   ├── openai_compat.py #   OpenAI / Qwen / DeepSeek
│       │   │   └── anthropic.py     #   Anthropic Claude
│       │   └── types.py
│       ├── alert/                   #   告警引擎
│       ├── logpipe/                 #   日志管道 + 异常检测
│       ├── monitor/                 #   系统监控
│       └── core/                    #   Runbook 引擎 + Session 管理
├── tests/                           #   单元测试
├── pyproject.toml                   #   项目配置 + 依赖声明
├── Makefile                         #   常用命令
└── README.md                        #   项目文档
```

---

## API 协议

### 请求格式

```json
{
  "query": "查看磁盘空间",
  "user_id": "admin",
  "session_id": "uuid (可选，自动生成)"
}
```

### 响应格式

safe（正常执行）：
```json
{
  "status": "success",
  "data": {
    "stdout": "Filesystem  Size  Used Avail Use%\n/dev/sda1  50G   20G   28G  42% /",
    "stderr": "",
    "rc": 0
  },
  "audit_id": "uuid"
}
```

unsafe（被拦截）：
```json
{
  "status": "rejected",
  "reason": "Intent classified as unsafe",
  "detail": "unsafe_file_delete"
}
```

needs-review（需人工）：
```json
{
  "status": "needs_review",
  "reason": "Query requires human review",
  "detail": "needs_review_sensitive"
}
```

---

## 常见问题

### Q: 麒麟OS 部署报 `ModuleNotFoundError: No module named 'transformers'`

```bash
# 确保用 .venv 里的 pip
source /opt/gcode/.venv/bin/activate
pip install -e ".[reasoner-openai]"
```

### Q: 如何不用 LLM 直接测试 Tool？

```bash
# 直接启动 MCP Server，用 stdio 模式测试
python -m gcode.mcp.server
```

### Q: 查看日志？

```bash
journalctl -u gcode-security-guard -u gcode-mcp-server -f
```

### Q: 如何卸载？

```bash
sudo systemctl stop gcode-security-guard gcode-mcp-server
sudo systemctl disable gcode-security-guard gcode-mcp-server
sudo rm /etc/systemd/system/gcode-*.service
sudo rm -rf /opt/gcode /run/gcode
```

---

## 开发

```bash
make install   # 安装开发依赖
make test      # 运行测试
make lint      # 代码检查
```

## 许可证

MIT License
