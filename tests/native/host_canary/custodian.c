/* Linux Host Canary custodian. Build/syntax checking is permitted; offline
 * tests MUST NOT execute this program. No fixture/worker integration is enabled.
 * Requires existing CLONE_NEWPID privilege, procfs, clone3/pidfds, ptrace,
 * close_range and seccomp. Never acquires privilege or changes host policy.
 * AF_UNIX SOCK_SEQPACKET protocol: BIRTH+pidfd/nsfd; START; durably ACKed
 * TASK births/exits; DONE; STOP; kernel init wait; CLOSED. Any error preserves.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/audit.h>
#include <linux/capability.h>
#include <linux/filter.h>
#include <linux/nsfs.h>
#include <linux/sched.h>
#include <linux/seccomp.h>
#include <poll.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/prctl.h>
#include <sys/ptrace.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static int control = -1, child_pidfd = -1;
static pid_t child_pid = -1;
#define LIMIT 4096
#define EVENTS 100000
#define BOUND_MS 30000

static int64_t milliseconds(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) return -1;
    return (int64_t)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}
static int64_t deadline(void) {
    int64_t now = milliseconds();
    return now < 0 ? -1 : now + BOUND_MS;
}
/* One absolute deadline, including EINTR and zero-progress retries. */
static int remaining(int64_t end) {
    int64_t now = milliseconds();
    if (end < 0 || now < 0 || now >= end) return -1;
    return (int)(end - now);
}
static int wait_readable(int fd, int64_t end) {
    for (;;) {
        int left = remaining(end);
        if (left < 0) return -1;
        struct pollfd item = {.fd = fd, .events = POLLIN};
        int n = poll(&item, 1, left);
        if (n < 0 && errno == EINTR) continue;
        return n == 1 && (item.revents & POLLIN) && !(item.revents & (POLLERR | POLLNVAL)) ? 0 : -1;
    }
}
static ssize_t receive(int fd, char *data, size_t capacity, int64_t end) {
    if (wait_readable(fd, end)) return -1;
    ssize_t n = recv(fd, data, capacity, MSG_TRUNC | MSG_DONTWAIT);
    return n > 0 && n < (ssize_t)capacity ? n : -1;
}
static int send_packet(int fd, const char *data) {
    size_t n = strlen(data);
    return send(fd, data, n, MSG_NOSIGNAL | MSG_DONTWAIT) == (ssize_t)n ? 0 : -1;
}
static int expect(int fd, const char *text, int64_t end) {
    char data[192];
    ssize_t n = receive(fd, data, sizeof(data), end);
    return n == (ssize_t)strlen(text) && !memcmp(data, text, (size_t)n) ? 0 : -1;
}
static int request(const char *verb, const char *session) {
    char text[128];
    int n = snprintf(text, sizeof(text), "%s %s", verb, session);
    return n > 0 && n < (int)sizeof(text) ? expect(control, text, deadline()) : -1;
}
static int wait_contained(void) {
    int64_t end = deadline();
    for (;;) {
        if (remaining(end) < 0) return -1;
        siginfo_t info = {0};
        if (waitid(P_PIDFD, (id_t)child_pidfd, &info, WEXITED | WNOHANG)) {
            if (errno == EINTR) continue; /* deadline checked before retry */
            return -1;
        }
        /* Kernel namespace shutdown precedes init becoming waitable; pidfd
         * readability, a successful signal or a worker exit is insufficient. */
        if (info.si_pid) {
            return info.si_pid == child_pid && info.si_code == CLD_KILLED &&
                   info.si_status == SIGKILL ? 0 : -1;
        }
        struct timespec pause = {.tv_nsec = 10000000};
        if (nanosleep(&pause, NULL) && errno != EINTR) return -1;
    }
}
static int kill_contained(void) {
    if (child_pidfd < 0) return -1;
    if (syscall(SYS_pidfd_send_signal, child_pidfd, SIGKILL, NULL, 0) && errno != ESRCH) return -1;
    return wait_contained();
}
static void preserve(void) {
    /* Best effort process containment only: never emits a closure receipt. */
    if (child_pidfd >= 0) (void)kill_contained();
    _exit(70);
}
static int birth_packet(const char *data, const int *fds) {
    struct iovec iov = {.iov_base = (void *)data, .iov_len = strlen(data)};
    char ancillary[CMSG_SPACE(sizeof(int) * 2)] = {0};
    struct msghdr msg = {.msg_iov = &iov, .msg_iovlen = 1,
                        .msg_control = ancillary, .msg_controllen = sizeof(ancillary)};
    struct cmsghdr *header = CMSG_FIRSTHDR(&msg);
    header->cmsg_level = SOL_SOCKET; header->cmsg_type = SCM_RIGHTS;
    header->cmsg_len = CMSG_LEN(sizeof(int) * 2);
    memcpy(CMSG_DATA(header), fds, sizeof(int) * 2);
    return sendmsg(control, &msg, MSG_NOSIGNAL | MSG_DONTWAIT) == (ssize_t)strlen(data) ? 0 : -1;
}

/* No capability gain, namespace escape, external-service/network delegation or
 * ptrace escape in the supported worker contract. Forks/threads are traced, not
 * denied. This is cooperative custody, not a general hostile-code sandbox. */
static int worker_filter(void) {
#if defined(__x86_64__)
#define THIS_ARCH AUDIT_ARCH_X86_64
#elif defined(__aarch64__)
#define THIS_ARCH AUDIT_ARCH_AARCH64
#else
#error unsupported seccomp architecture
#endif
#define DENY(n) BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_##n, 0, 1), BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM)
    struct sock_filter code[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, arch)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, THIS_ARCH, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
#if defined(__x86_64__)
        /* Refuse the x32 ABI before interpreting native syscall numbers. */
        BPF_JUMP(BPF_JMP | BPF_JSET | BPF_K, 0x40000000, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
#endif
        /* clone3's pointed-to flags cannot be inspected by classic seccomp.
         * Force libc's legacy fallback; deny untraced/new-namespace clones. */
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_clone3, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | ENOSYS),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_clone, 0, 3),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, args[0])),
        BPF_JUMP(BPF_JMP | BPF_JSET | BPF_K, CLONE_UNTRACED | CLONE_NEWUSER | CLONE_NEWPID |
                 CLONE_NEWNS | CLONE_NEWNET | CLONE_NEWIPC | CLONE_NEWUTS | CLONE_NEWCGROUP, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
        DENY(setns), DENY(unshare), DENY(mount), DENY(umount2),
        DENY(ptrace), DENY(process_vm_writev), DENY(pidfd_getfd),
        DENY(socket), DENY(socketpair), DENY(connect), DENY(sendto), DENY(sendmsg),
        DENY(io_uring_setup), DENY(bpf),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW)
    };
    struct sock_fprog program = {.len = (unsigned short)(sizeof(code) / sizeof(code[0])), .filter = code};
    struct __user_cap_header_struct head = {.version = _LINUX_CAPABILITY_VERSION_3, .pid = 0};
    struct __user_cap_data_struct caps[2] = {{0}};
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) ||
        syscall(SYS_capset, &head, caps) ||
        prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0)) return -1;
    return prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program);
#undef DENY
}

struct task { pid_t pid; int alive; };
static struct task tasks[LIMIT];
static unsigned long sequence;
static int active;
static int known(pid_t pid) {
    for (int i = 0; i < LIMIT; ++i) if (tasks[i].alive && tasks[i].pid == pid) return i;
    return -1;
}
/* A newborn tracee may report SIGSTOP before its creator's fork event (Linux
 * wakes it before ptrace_event_pid). Never consume/adopt unknown PID statuses.
 * Wait only already registered tasks until their creator registers the child. */
static pid_t wait_known(int *status) {
    for (int i = 0; i < LIMIT; ++i) if (tasks[i].alive) {
        pid_t got = waitpid(tasks[i].pid, status, __WALL | WNOHANG);
        if (got < 0 && errno == EINTR) return 0;
        if (got) return got;
    }
    return 0;
}
static int event(int gate, const char *session, const char *kind, pid_t pid, int value, int64_t end) {
    if (++sequence > EVENTS) return -1;
    char data[192], ack[128];
    int n = snprintf(data, sizeof(data), "TASK %s %lu %s %ld %d", session, sequence, kind, (long)pid, value);
    int m = snprintf(ack, sizeof(ack), "ACK %s %lu", session, sequence);
    return n > 0 && n < (int)sizeof(data) && m > 0 && m < (int)sizeof(ack) &&
           !send_packet(gate, data) ? expect(gate, ack, end) : -1;
}
static int born(int gate, const char *session, pid_t pid, pid_t parent, int64_t end) {
    if (pid <= 1 || known(pid) >= 0 || active >= LIMIT) return -1;
    int index = -1;
    for (int i = 0; i < LIMIT; ++i) if (!tasks[i].alive) { index = i; break; }
    if (index < 0 || event(gate, session, "BIRTH", pid, parent, end)) return -1;
    tasks[index] = (struct task){.pid = pid, .alive = 1}; ++active;
    return 0;
}
static void namespace_init(int gate, int ready, int root, const char *session, char **worker) {
    if (getpid() != 1 || prctl(PR_SET_PDEATHSIG, SIGKILL)) _exit(71);
    if (syscall(SYS_close_range, 3U, ~0U, CLOSE_RANGE_CLOEXEC)) _exit(72);
    if (write(ready, "R", 1) != 1) _exit(73);
    close(ready);
    char start[128];
    snprintf(start, sizeof(start), "START %s", session);
    if (expect(gate, start, deadline())) _exit(74);
    int64_t end = deadline(); /* single bounded entire worker run */
    pid_t worker_pid = fork();
    if (worker_pid < 0) _exit(75);
    if (!worker_pid) {
        close(gate);
        /* Retain just the approved directory capability across exec. */
        if (fcntl(root, F_SETFD, 0)) _exit(80);
        char paths[10][128];
        const char *roles[] = {"home", "config", "data", "cache", "state", "runtime", "tmp", "system-config", "system-data", "home"};
        for (int i = 0; i < 10; ++i) {
            int n = snprintf(paths[i], sizeof(paths[i]), "/proc/self/fd/%d/%s", root, roles[i]);
            if (n <= 0 || n >= (int)sizeof(paths[i])) _exit(81);
        }
        if (fchdir(root)) _exit(82);
        if (clearenv() || setenv("PATH", "/usr/bin:/bin", 1) || setenv("LANG", "C", 1)) _exit(83);
        const char *keys[] = {"HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR", "TMPDIR", "XDG_CONFIG_DIRS", "XDG_DATA_DIRS", "PANDA_CANARY_HOME"};
        for (int i = 0; i < 10; ++i) if (setenv(keys[i], paths[i], 1)) _exit(84);
        if (ptrace(PTRACE_TRACEME, 0, NULL, NULL) || raise(SIGSTOP)) _exit(85);
        if (worker_filter()) _exit(86);
        execv(worker[0], worker);
        _exit(127);
    }
    int status, root_status = -1;
    pid_t got;
    do { got = waitpid(worker_pid, &status, WUNTRACED | WNOHANG); }
    while (!got && remaining(end) > 0);
    if (got != worker_pid || !WIFSTOPPED(status) || WSTOPSIG(status) != SIGSTOP) _exit(87);
    unsigned long options = PTRACE_O_TRACEFORK | PTRACE_O_TRACEVFORK | PTRACE_O_TRACECLONE |
                            PTRACE_O_TRACEEXEC | PTRACE_O_TRACEEXIT | PTRACE_O_EXITKILL;
    if (ptrace(PTRACE_SETOPTIONS, worker_pid, NULL, (void *)options) ||
        born(gate, session, worker_pid, 1, end) || ptrace(PTRACE_CONT, worker_pid, NULL, NULL)) _exit(88);
    while (active) {
        if (remaining(end) < 0) _exit(89);
        got = wait_known(&status);
        if (got < 0 && errno == EINTR) continue;
        if (got < 0) _exit(90);
        if (!got) { struct timespec pause = {.tv_nsec = 1000000}; nanosleep(&pause, NULL); continue; }
        int index = known(got);
        if (index < 0) _exit(91); /* never adopt an unregistered descendant */
        if (WIFEXITED(status) || WIFSIGNALED(status)) {
            int result = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
            if (event(gate, session, "EXIT", got, result, end)) _exit(92);
            tasks[index].alive = 0; --active;
            if (got == worker_pid && root_status < 0) root_status = result;
            continue;
        }
        if (!WIFSTOPPED(status)) _exit(93);
        unsigned int kind = (unsigned int)status >> 16;
        if (kind == PTRACE_EVENT_FORK || kind == PTRACE_EVENT_VFORK || kind == PTRACE_EVENT_CLONE) {
            unsigned long child = 0;
            if (ptrace(PTRACE_GETEVENTMSG, got, NULL, &child) || child > INT_MAX ||
                born(gate, session, (pid_t)child, got, end)) _exit(94);
        } else if (kind == PTRACE_EVENT_EXEC) {
            unsigned long previous = 0;
            if (ptrace(PTRACE_GETEVENTMSG, got, NULL, &previous) || previous != (unsigned long)got) _exit(95);
            /* Nonleader exec/TID replacement requires a new reviewed transition. */
        } else if (kind != 0 && kind != PTRACE_EVENT_EXIT) _exit(96);
        int sig = kind || WSTOPSIG(status) == SIGSTOP ? 0 : WSTOPSIG(status);
        if (ptrace(PTRACE_CONT, got, NULL, (void *)(long)sig)) _exit(97);
    }
    /* There must be no unknown live or waitable descendant. A zero result
     * means an unregistered live child, not successful completion. */
    errno = 0;
    got = waitpid(-1, &status, __WALL | WNOHANG);
    if (got != -1 || errno != ECHILD) _exit(100);
    if (root_status < 0) _exit(98);
    char done[128];
    snprintf(done, sizeof(done), "DONE %s %d", session, root_status);
    if (send_packet(gate, done)) _exit(99);
    /* Init remains alive; only retained pidfd STOP + actual wait establishes end. */
    for (;;) pause();
}

int main(int argc, char **argv) {
    if (argc < 8 || strcmp(argv[1], "--control-fd") || strcmp(argv[4], "--root-fd") ||
        strcmp(argv[6], "--") || strlen(argv[3]) != 32 || argv[7][0] != '/') return 64;
    for (size_t i = 0; i < 32; ++i) if (!((argv[3][i] >= '0' && argv[3][i] <= '9') ||
        (argv[3][i] >= 'a' && argv[3][i] <= 'f'))) return 64;
    char *tail;
    long selected = strtol(argv[2], &tail, 10);
    if (*tail || selected < 3 || selected > 1048576) return 64;
    control = (int)selected;
    selected = strtol(argv[5], &tail, 10);
    if (*tail || selected < 3 || selected > 1048576 || selected == control) return 64;
    int root = (int)selected;
    struct stat root_stat;
    if (fstat(root, &root_stat) || !S_ISDIR(root_stat.st_mode) || root_stat.st_uid != getuid() ||
        (root_stat.st_mode & 0777) != 0700 || !getuid()) return 65;
    int type = 0; socklen_t size = sizeof(type);
    if (getsockopt(control, SOL_SOCKET, SO_TYPE, &type, &size) || type != SOCK_SEQPACKET) return 65;
    int gate[2], ready[2];
    if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, gate) || pipe2(ready, O_CLOEXEC)) return 66;
    struct clone_args args = {0};
    args.flags = CLONE_NEWPID | CLONE_PIDFD;
    args.pidfd = (uintptr_t)&child_pidfd; args.exit_signal = SIGCHLD;
    child_pid = (pid_t)syscall(SYS_clone3, &args, sizeof(args));
    if (child_pid < 0) return 67;
    if (!child_pid) {
        close(control); close(gate[1]); close(ready[0]);
        namespace_init(gate[0], ready[1], root, argv[3], &argv[7]);
        _exit(78);
    }
    close(gate[0]); close(ready[1]);
    int64_t end = deadline();
    if (wait_readable(ready[0], end)) preserve();
    char token;
    if (read(ready[0], &token, 1) != 1 || token != 'R') preserve();
    close(ready[0]);
    char path[96];
    int n = snprintf(path, sizeof(path), "/proc/%ld/ns/pid", (long)child_pid);
    if (n <= 0 || n >= (int)sizeof(path)) preserve();
    int namespace_fd = open(path, O_RDONLY | O_CLOEXEC);
    int parent_namespace = namespace_fd >= 0 ? ioctl(namespace_fd, NS_GET_PARENT) : -1;
    int self_namespace = open("/proc/self/ns/pid", O_RDONLY | O_CLOEXEC);
    struct stat ns, parent, self;
    if (namespace_fd < 0 || parent_namespace < 0 || self_namespace < 0 ||
        ioctl(namespace_fd, NS_GET_NSTYPE) != CLONE_NEWPID || fstat(namespace_fd, &ns) ||
        fstat(parent_namespace, &parent) || fstat(self_namespace, &self) ||
        parent.st_dev != self.st_dev || parent.st_ino != self.st_ino ||
        (ns.st_dev == self.st_dev && ns.st_ino == self.st_ino)) preserve();
    close(parent_namespace); close(self_namespace);
    char message[192];
    snprintf(message, sizeof(message), "BIRTH %s %ld %llu %llu %llu", argv[3], (long)child_pid,
             (unsigned long long)ns.st_ino, (unsigned long long)root_stat.st_dev,
             (unsigned long long)root_stat.st_ino);
    int fds[2] = {child_pidfd, namespace_fd};
    if (birth_packet(message, fds) || request("START", argv[3])) preserve();
    snprintf(message, sizeof(message), "START %s", argv[3]);
    if (send_packet(gate[1], message)) preserve();
    end = deadline();
    for (;;) {
        char data[192], ack[192];
        ssize_t count = receive(gate[1], data, sizeof(data), end);
        if (count < 0) preserve();
        data[count] = 0;
        if (send_packet(control, data)) preserve();
        if (!strncmp(data, "DONE ", 5)) break;
        if (strncmp(data, "TASK ", 5)) preserve();
        count = receive(control, ack, sizeof(ack), end);
        if (count < 0) preserve();
        ack[count] = 0;
        if (send_packet(gate[1], ack)) preserve();
    }
    if (request("STOP", argv[3]) || kill_contained()) preserve();
    close(child_pidfd); child_pidfd = -1;
    snprintf(message, sizeof(message), "CLOSED %s", argv[3]);
    if (send_packet(control, message)) _exit(79);
    close(gate[1]); close(namespace_fd);
    return 0;
}
