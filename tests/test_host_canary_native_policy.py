"""Pure Python execution of the native classic-BPF initializer, never a binary.

Models the documented Linux x86_64 seccomp ABI. No worker, mount, process or
filesystem adapter is invoked. This cannot establish kernel custody.
"""
import os
from pathlib import Path
import re
import unittest

SOURCE = (Path(__file__).parent / 'native/host_canary/custodian.c').read_text()
NUMBERS = dict(read=0, write=1, open=2, close=3, stat=4, fstat=5, lstat=6,
              poll=7, lseek=8, mmap=9, mprotect=10, munmap=11, brk=12,
              rt_sigaction=13, rt_sigprocmask=14, rt_sigreturn=15, ioctl=16,
              pread64=17, pwrite64=18, readv=19, writev=20, access=21,
              pipe=22, sched_yield=24, mremap=25, madvise=28, dup=32, dup2=33,
              nanosleep=35, getpid=39, socket=41, connect=42, sendto=44,
              recvfrom=45, sendmsg=46, recvmsg=47, clone=56, fork=57, vfork=58,
              execve=59, exit=60, wait4=61, kill=62, uname=63, fcntl=72,
              fsync=74, truncate=76, ftruncate=77, getdents=78, getcwd=79,
              chdir=80, fchdir=81, rename=82, mkdir=83, rmdir=84, creat=85,
              link=86, unlink=87, symlink=88, readlink=89, chmod=90,
              fchmod=91, chown=92, fchown=93, lchown=94, umask=95,
              gettimeofday=96, getuid=102, getgid=104, geteuid=107,
              getegid=108, getppid=110, capset=126, rt_sigsuspend=130,
              sigaltstack=131, arch_prctl=158, prctl=157, mount=165,
              setxattr=188, gettid=186, futex=202, getdents64=217,
              set_tid_address=218, clock_gettime=228, clock_nanosleep=230,
              exit_group=231, openat=257, mkdirat=258, newfstatat=262,
              unlinkat=263, renameat=264, readlinkat=267, fchmodat=268,
              faccessat=269, pselect6=270, ppoll=271, set_robust_list=273,
              utimensat=280, dup3=292, preadv=295, pwritev=296,
              prlimit64=302, getrandom=318, execveat=322, statx=332,
              rseq=334, clone3=435, close_range=436, openat2=437)
CONSTANTS = dict(THIS_ARCH=0xc000003e, SECCOMP_RET_ALLOW=0x7fff0000,
                 SECCOMP_RET_TRACE=0x7ff00000,
                 SECCOMP_RET_ERRNO=0x50000, ENOTTY=25, F_GETFD=1, F_GETFL=3, TCGETS=0x5401, TCGETS2=0x802c542a,
                 SECCOMP_RET_TRAP=0x30000, SECCOMP_RET_KILL_PROCESS=0x80000000,
                 O_ACCMODE=3, O_WRONLY=1, O_RDWR=2, O_CREAT=64, O_EXCL=128,
                 O_TRUNC=512, O_APPEND=1024, O_TMPFILE=0x410000,
                 MAP_SHARED=1, PROT_WRITE=2)


def constant(value):
    value = value.strip()
    if ' + ' in value: return sum(constant(item) for item in value.split(' + '))
    if value.startswith('__NR_'): return NUMBERS[value[5:]]
    if value in CONSTANTS: return CONSTANTS[value]
    if value.startswith('offsetof('):
        field = value.split(', ', 1)[1][:-1]
        if field == 'arch': return 4
        if field == 'nr': return 0
        return 16 + int(re.search(r'args\[(\d+)\]', field)[1]) * 8
    if '|' in value: return sum(constant(item) for item in value.split('|'))
    return int(value, 0)


def instructions():
    match = re.search(r'static const struct sock_filter mediated_code\[\] = \{(.*?)\n\};', SOURCE, re.S)
    if not match: raise AssertionError('mediated closed BPF policy missing')
    code = re.sub(r'/\*.*?\*/', '', match[1], flags=re.S)
    result = []
    for line in code.splitlines():
        line = line.strip().rstrip(',')
        if not line: continue
        allow = re.fullmatch(r'M_ALLOW\((\w+)\)', line)
        if allow:
            result.extend([('JEQ', NUMBERS[allow[1]], 0, 1), ('RET', 0x7fff0000)])
            continue
        stmt = re.fullmatch(r'BPF_STMT\(BPF_(LD|RET)(?: \| BPF_W \| BPF_ABS| \| BPF_K)?, (.*)\)', line)
        jump = re.fullmatch(r'BPF_JUMP\(BPF_JMP \| BPF_(JEQ|JSET|JGE) \| BPF_K, (.*), (\d+), (\d+)\)', line)
        if stmt: result.append((stmt[1], constant(stmt[2])))
        elif jump: result.append((jump[1], constant(jump[2]), int(jump[3]), int(jump[4])))
        else: raise AssertionError('uninterpreted native BPF: ' + line)
    return result


def decision(name, *args, arch=0xc000003e):
    memory = {0: NUMBERS.get(name, name), 4: arch}
    for n in range(6):
        value = args[n] if n < len(args) else 0
        memory[16 + n * 8] = value & 0xffffffff
        memory[20 + n * 8] = (value >> 32) & 0xffffffff
    pc, accumulator, code = 0, 0, instructions()
    while pc < len(code):
        op, value, *branches = code[pc]
        if op == 'RET': return value
        if op == 'LD': accumulator = memory[value]
        else:
            condition = accumulator == value if op == 'JEQ' else bool(accumulator & value) if op == 'JSET' else accumulator >= value
            pc += branches[0 if condition else 1]
        pc += 1
    raise AssertionError('BPF fell through')


class NativePolicyTests(unittest.TestCase):
    def allowed(self, syscall, *args): self.assertEqual(decision(syscall, *args), 0x7fff0000)
    def denied(self, syscall, *args): self.assertNotEqual(decision(syscall, *args), 0x7fff0000)

    def test_inherited_runtime_descriptor_is_sealed_after_exec_handoff(self):
        # pass_fds preserves the parent's CLOEXEC original but clears the flag
        # in the exec'd helper copy. Requiring CLOEXEC at entry rejects every
        # valid handoff. The helper must immediately restore it before clone.
        self.assertIn('fcntl(runtime, F_GETFD) != 0 || fcntl(runtime, F_SETFD, FD_CLOEXEC)', SOURCE)

    def test_readonly_script_isatty_probe_returns_enotty_without_kernel_ioctl(self):
        for fd in (0,1,2,3,4,100):
            for request in (0x5401,0x802c542a):
                self.assertEqual(decision('ioctl',fd,request,0),0x50000|25)

    def test_default_refuses_mutation_delegation_and_fd_replacement(self):
        for name in ('pwrite64', 'pwritev', 'writev', 'rename', 'renameat', 'chmod', 'fchmod',
                     'chown', 'utimensat', 'truncate', 'ftruncate', 'mkdir', 'unlink', 'unlinkat',
                     'setxattr', 'socket', 'sendmsg', 'recvmsg', 'clone', 'clone3', 'fork',
                     'vfork', 'dup', 'dup2', 'dup3', 'fcntl', 'close_range', 'mount',
                     'execveat', 'openat2', 'ioctl', 9999):
            with self.subTest(syscall=name): self.denied(name)

    def test_open_checks_all_write_flags_even_with_readonly_access_mode(self):
        self.allowed('open', 0, os.O_RDONLY)
        self.allowed('openat', -100, 0, os.O_RDONLY | os.O_CLOEXEC)
        for flags in (1, 2, 3, 64, 128, 512, 1024, 0x410000):
            self.denied('open', 0, flags)
            self.denied('openat', -100, 0, flags)

    def test_rpc_stdio_writes_only_and_fixed_descriptors_cannot_be_replaced(self):
        for fd in (1, 2, 3): self.allowed('write', fd, 0, 10)
        for fd in (0, 4, 99, 0xffffffff): self.denied('write', fd, 0, 10)
        for fd in range(4): self.denied('close', fd)
        self.allowed('close', 4)

    def test_shared_memory_denied_including_readonly_later_mprotect_bypass(self):
        self.allowed('mmap', 0, 4096, 3, 2)
        self.denied('mmap', 0, 4096, 3, 1)
        self.denied('mmap', 0, 4096, 1, 1)

    def test_resource_limits_are_readonly_and_only_self(self):
        self.allowed('prlimit64', 0, 7, 0, 4096)
        self.denied('prlimit64', 1, 7, 0, 4096)
        self.denied('prlimit64', 0, 7, 4096, 0)
        self.denied('prlimit64', 0, 7, 0x100000000, 0)

    def test_wrong_arch_x32_and_unknown_syscall_refuse(self):
        self.assertNotEqual(decision('read', arch=0x40000003), 0x7fff0000)
        self.denied(0x40000000)
        self.denied(0x40000001)

    def test_exec_requires_tracer_decision_before_kernel_load(self):
        self.assertEqual(decision('execve'), 0x7ff00000)
        self.denied('execveat')

    def test_interpreter_readonly_descriptor_probes(self):
        for fd in (0, 1, 2, 3, 4):
            self.allowed('fcntl', fd, 1)
            self.allowed('fcntl', fd, 3)
        for command in (0, 2, 4, 6, 1030): self.denied('fcntl', 3, command)
        for fd in (0, 1, 2): self.assertEqual(decision('ioctl', fd, 0x5401), 0x50019)
        self.denied('ioctl', 3, 0x5401)
        self.denied('ioctl', 1, 0x5412)


if __name__ == '__main__': unittest.main()
