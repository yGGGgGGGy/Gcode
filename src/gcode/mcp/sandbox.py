"""执行沙箱 — seccomp + 资源限制 + 用户隔离

麒麟OS适配：通过 seccomp 限制系统调用，通过 prlimit 限制资源。
执行层以 agent-exec 用户运行，仅开放安全系统调用白名单。
"""
import resource
import os


# 安全系统调用白名单（readonly + metrics + 管理操作所需的最小集合）
ALLOWED_SYSCALLS = {
    "read", "write", "openat", "close", "fstat", "lseek",
    "mmap", "munmap", "brk", "mprotect",
    "rt_sigaction", "sigreturn",
    "clone", "execve", "exit_group", "wait4",
    "getpid", "getuid", "getgid", "getcwd",
    "stat", "statfs", "access", "readlink",
    "socket", "connect", "bind", "getsockname",
    "fcntl", "ioctl", "poll", "select",
    "writev", "readv", "sendto", "recvfrom",
    "nanosleep", "clock_gettime",
    "getdents64", "prlimit64",
}

# 资源限制
RESOURCE_LIMITS = {
    resource.RLIMIT_CPU: (30, 30),       # 30 秒 CPU 时间
    resource.RLIMIT_AS: (512 * 1024**2, 512 * 1024**2),  # 512MB 内存
    resource.RLIMIT_NOFILE: (64, 64),    # 64 个文件描述符
    resource.RLIMIT_NPROC: (16, 16),     # 16 个进程
}


def apply_limits():
    """应用资源限制到当前进程"""
    for rlimit, (soft, hard) in RESOURCE_LIMITS.items():
        try:
            resource.setrlimit(rlimit, (soft, hard))
        except Exception:
            pass  # 无权限时不阻塞


def drop_privileges(uid: int, gid: int):
    """降权到 agent-exec 用户"""
    try:
        os.setgid(gid)
        os.setuid(uid)
    except OSError:
        pass  # 非 root 运行时不可用


def generate_seccomp_profile() -> str:
    """生成 seccomp-bpf 规则字符串（麒麟 Linux 4.19+ 兼容）"""
    # 实际部署时使用 seccomp Python 绑定或 libseccomp
    # 此处返回配置概要，由 systemd 单元或 podman 应用
    return f"""
# Gcode seccomp profile
# Allowed syscalls count: {len(ALLOWED_SYSCALLS)}
# Apply via: systemd SystemCallFilter= or podman --security-opt seccomp=
SystemCallFilter={' '.join(sorted(ALLOWED_SYSCALLS))}
SystemCallErrorNumber=EPERM
"""
