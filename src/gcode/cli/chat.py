"""Gcode 自然语言聊天界面 — 直接打字，无需 JSON/Socket 命令。

用法:
  gcode                    # 交互模式（自动启动后端）
  gcode 查看磁盘空间         # 单次查询
  gcode --history          # 查看历史会话
  gcode --stop             # 停止后端服务
"""

import io
import json
import os
import signal
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime

# 强制 stdin/stdout 使用 UTF-8（兼容 locale 未设置的环境）
if sys.stdin.encoding and sys.stdin.encoding.lower() != "utf-8":
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SOCKET_PATH = os.environ.get("GCODE_SOCKET", "/run/gcode/gcode.sock")
PID_DIR = "/run/gcode"
GUARD_PID_FILE = os.path.join(PID_DIR, "gcode-guard.pid")
MCP_PID_FILE = os.path.join(PID_DIR, "gcode-mcp.pid")
GCODE_DIR = os.environ.get("GCODE_DIR", "/opt/gcode")


def _is_socket_alive(path: str) -> bool:
    """检查 Unix Socket 是否可连接"""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect(path)
        sock.close()
        return True
    except (FileNotFoundError, ConnectionRefusedError, socket.timeout, OSError):
        return False


def _read_pid(pid_file: str) -> int | None:
    """读取 PID 文件"""
    try:
        with open(pid_file) as f:
            pid = int(f.read().strip())
        # 检查进程是否还活着
        os.kill(pid, 0)
        return pid
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return None


def _start_backend() -> bool:
    """自动启动后端服务"""
    # 确保 socket 目录存在
    os.makedirs(PID_DIR, mode=0o770, exist_ok=True)

    python = os.path.join(GCODE_DIR, ".venv", "bin", "python")
    if not os.path.isfile(python):
        python = "python3"

    started = False

    # 启动 Security Guard
    if not _read_pid(GUARD_PID_FILE):
        print("  启动安全层 (security-guard)...")
        proc = subprocess.Popen(
            [python, "-m", "src.api.server"],
            cwd=GCODE_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        with open(GUARD_PID_FILE, "w") as f:
            f.write(str(proc.pid))
        started = True

    # 启动 MCP Server
    if not _read_pid(MCP_PID_FILE):
        print("  启动执行层 (mcp-server)...")
        proc = subprocess.Popen(
            [python, "-m", "gcode.mcp.server"],
            cwd=GCODE_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        with open(MCP_PID_FILE, "w") as f:
            f.write(str(proc.pid))
        started = True

    if started:
        # 等待 socket 就绪
        print("  等待服务就绪...")
        for _ in range(15):
            time.sleep(1)
            if _is_socket_alive(SOCKET_PATH):
                print("  服务已就绪\n")
                return True
        print("  [警告] 服务启动超时，可能需要手动检查\n")
        return False

    return True


def stop_backend():
    """停止后端服务"""
    stopped = False
    for name, pid_file in [("security-guard", GUARD_PID_FILE), ("mcp-server", MCP_PID_FILE)]:
        pid = _read_pid(pid_file)
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                print(f"  已停止 {name} (PID {pid})")
                stopped = True
            except ProcessLookupError:
                pass
            try:
                os.remove(pid_file)
            except FileNotFoundError:
                pass
    if not stopped:
        print("  没有运行中的后端服务")
    else:
        # 清理 socket
        try:
            os.remove(SOCKET_PATH)
        except FileNotFoundError:
            pass


def ensure_backend():
    """确保后端服务正在运行"""
    if _is_socket_alive(SOCKET_PATH):
        return True
    return _start_backend()


def send_query(query: str, user_id: str = "admin", session_id: str | None = None) -> dict:
    """通过 Unix Socket 发送自然语言查询给 Gcode Agent"""
    if session_id is None:
        session_id = str(uuid.uuid4())

    request = {"query": query, "user_id": user_id, "session_id": session_id}

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(30)
        sock.connect(SOCKET_PATH)
        sock.sendall(json.dumps(request, ensure_ascii=False).encode() + b"\n")
        raw = sock.recv(65536)
        sock.close()
        return json.loads(raw)
    except FileNotFoundError:
        return {"status": "error", "error": "Gcode 服务未启动。请运行: gcode（会自动启动服务）"}
    except ConnectionRefusedError:
        return {"status": "error", "error": "无法连接到 Gcode 服务，后端可能正在启动中，请稍后重试"}
    except socket.timeout:
        return {"status": "error", "error": "请求超时，请重试"}


def format_result(result: dict) -> str:
    """格式化返回结果，让人能看懂"""
    status = result.get("status", "unknown")

    if status == "error":
        return f"[错误] {result.get('error', '未知错误')}"

    if status == "rejected":
        reason = result.get("reason", "未知原因")
        detail = result.get("detail", "")
        return f"[操作被拦截]\n原因: {reason}\n详情: {detail}\n\n该操作可能存在安全风险，已被自动拦截。如需执行，请联系管理员。"

    if status == "needs_review":
        reason = result.get("reason", "")
        detail = result.get("detail", "")
        return f"[需要人工审核]\n说明: {reason}\n详情: {detail}\n\n此操作涉及敏感资源，需要管理员审批后执行。"

    if status == "success":
        data = result.get("data", {})
        output = ""

        # MCP Tool 执行结果
        if isinstance(data, dict):
            stdout = data.get("stdout", "")
            stderr = data.get("stderr", "")
            warnings = data.get("warnings", [])
            needs_confirmation = data.get("needs_confirmation", False)
            dry_run = data.get("dry_run", "")

            if dry_run:
                output += f"[预览]\n{dry_run}\n\n[需要确认才能执行]"
            elif stdout:
                output += stdout
            if stderr:
                output += f"\n[stderr]\n{stderr}"
            if warnings:
                for w in warnings:
                    output += f"\n{w}"
            if needs_confirmation and not dry_run:
                output += "\n\n[此操作需要确认后才能执行]"
        else:
            output = str(data)

        audit_id = result.get("audit_id", "")
        if audit_id:
            output += f"\n\n审计ID: {audit_id}"

        return output or "[操作完成，无返回内容]"

    return json.dumps(result, ensure_ascii=False, indent=2)


def interactive_loop(user_id: str = "admin"):
    """交互式聊天模式"""
    banner = f"""
  ╔══════════════════════════════════╗
  ║      Gcode 智能运维Agent        ║
  ║   用自然语言管理麒麟OS服务器      ║
  ╚══════════════════════════════════╝

  输入问题开始，例如:
    · 查看磁盘空间
    · CPU 使用率多少
    · nginx 服务状态怎么样
    · 查看最近 50 条系统日志

  输入 quit 或 Ctrl+C 退出
  输入 history 查看会话记录
  """
    print(banner)

    session_id = str(uuid.uuid4())
    print(f"会话ID: {session_id[:8]}...\n")

    while True:
        try:
            try:
                query = input(">> ").strip()
            except UnicodeDecodeError:
                # 终端编码非 UTF-8 时，从 buffer 读取原始字节再解码
                raw = sys.stdin.buffer.readline()
                query = raw.decode("utf-8", errors="replace").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not query:
            continue

        if query.lower() in ("quit", "exit", "q"):
            print("再见！")
            break

        if query.lower() == "history":
            show_history()
            continue

        print(f"[{datetime.now().strftime('%H:%M:%S')}] 处理中...")
        result = send_query(query, user_id=user_id, session_id=session_id)
        print()
        print(format_result(result))
        print()


def show_history():
    """显示最近的审计记录"""
    print("\n审计记录（最近 10 条）:")
    try:
        import sqlite3
        db_path = os.environ.get("GCODE_AUDIT_DB", "/opt/gcode/data/audit/gcode.db")
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT created_at, original_query, final_status FROM audit_records ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        if not rows:
            print("  (暂无记录)")
        for row in rows:
            ts, query, status = row
            print(f"  {ts} [{status}] {query[:60]}")
        conn.close()
    except Exception as e:
        print(f"  无法读取审计记录: {e}")
    print()


def main():
    import argparse
    global SOCKET_PATH
    parser = argparse.ArgumentParser(description="Gcode 智能运维 Agent — 自然语言操作系统")
    parser.add_argument("query", nargs="*", help="运维问题（自然语言）")
    parser.add_argument("--user", "-u", default="admin", help="用户名")
    parser.add_argument("--socket", "-s", default=SOCKET_PATH, help="Unix Socket 路径")
    parser.add_argument("--history", action="store_true", help="查看审计记录")
    parser.add_argument("--stop", action="store_true", help="停止后端服务")
    args = parser.parse_args()

    SOCKET_PATH = args.socket

    if args.stop:
        stop_backend()
        return

    if args.history:
        show_history()
        return

    # 确保后端服务运行
    ensure_backend()

    if args.query:
        # 单次查询模式
        query = " ".join(args.query)
        print(f">> {query}")
        result = send_query(query, user_id=args.user)
        print(format_result(result))
    else:
        # 交互模式
        interactive_loop(user_id=args.user)


if __name__ == "__main__":
    main()
