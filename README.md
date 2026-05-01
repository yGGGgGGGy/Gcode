# Gcode — 麒麟OS 智能运维Agent

**对话式高效运维，杜绝误操作与安全风险。**

通过 MCP 协议实现自然语言与 OS 交互，配合三层安全护栏（意图过滤 + 最小权限 + 思维链审计）确保每次操作都可控、可审计。

## 架构

```
用户自然语言
    ↓
┌─────────────────────────────────────────┐
│  gcode-security-guard (m1)              │
│  ├ 意图风险过滤（入口）                   │
│  ├ 推理层 — LLM Runtime                 │
│  └ 思维链审计（全链路）                    │
└───────────────┬─────────────────────────┘
                ↓ Unix Domain Socket
┌─────────────────────────────────────────┐
│  gcode-mcp-server (dp1)                 │
│  ├ MCP 协议 Server（FastMCP）            │
│  ├ 三层分级 Tool（只读/指标/管理）         │
│  └ 执行层（seccomp + 资源限制）           │
└───────────────┬─────────────────────────┘
                ↓
           麒麟OS（systemd / rpm / journalctl / ...）
```

## 安全护栏

| 层 | 职责 | 负责人 |
|----|------|--------|
| 意图过滤（入口） | 正则拦截高危命令 + 小模型意图分类 | m1 |
| 最小权限（出口） | 参数校验 + dry-run确认 + seccomp沙箱 | dp1 |
| 思维链审计（全链路） | SQLite全量记录 + DAG回放 + 异常检测 | m1 |

## 项目结构

```
src/
├── contracts/         # m1↔dp1 接口契约
│   └── types.py       # SessionContext, ToolCallRecord, ToolResult
└── gcode/
    ├── alert/         # 告警引擎
    ├── cli/           # CLI 入口
    ├── core/          # Runbook 引擎 + Session 管理
    ├── logpipe/       # 日志管道 + 异常检测
    ├── monitor/       # 系统监控
    ├── report/        # 报告生成
    └── mcp/           # MCP Server + 执行层
        ├── server.py
        ├── executor.py
        ├── sandbox.py
        ├── tools_readonly.py
        ├── tools_metrics.py
        └── tools_management.py
```

## 快速开始

```bash
pip install -e .

# 启动 MCP Server（stdio 模式）
python -m gcode.mcp.server

# 启动 CLI
python -m gcode.cli.main
```

## MCP Tool 列表

### 只读感知（risk: read_only）

| Tool | 功能 |
|------|------|
| `sys_info` | 系统信息（内核、架构、麒麟版本） |
| `ps_list` | 进程列表 |
| `df_h` | 磁盘使用 |
| `netstat` | 网络连接 |
| `journalctl` | 系统日志 |

### 指标采集（risk: read_only）

| Tool | 功能 |
|------|------|
| `cpu_usage` | CPU 使用率 |
| `mem_usage` | 内存 + Swap |
| `io_stat` | 磁盘 IO |
| `disk_health` | 磁盘健康 |

### 管理执行（risk: admin，需确认）

| Tool | 功能 |
|------|------|
| `service_status` | 服务状态 |
| `service_restart` | 重启服务 |
| `pkg_install` | 安装 RPM 包 |

## 麒麟OS 适配

- dnf/rpm 包管理
- systemd 服务管理
- SELinux 安全策略兼容
- auditd 审计日志打通

## 配对仓库

- [gcode-mcp-server](https://github.com/yGGGgGGGy/gcode-mcp-server) — 执行层（dp1）
- [gcode-security-guard](https://github.com/yGGGgGGGy/gcode-security-guard) — 安全层（m1）
