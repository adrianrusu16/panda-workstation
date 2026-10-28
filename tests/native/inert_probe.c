/* Source/build review only. No Qt, bus, display, sensor, network endpoint or GUI.
 * Fixed inputs and stdout records; no executable/path/command arguments.
 * The outer boundary MUST contain the ELF interpreter and libc before main.
 */
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <limits.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/ptrace.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

#if !defined(__x86_64__) || defined(__ILP32__)
#error "Reviewed policy supports Linux x86-64 only"
#endif

static int no_exec(void)
{
    struct sock_filter filter[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, arch)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AUDIT_ARCH_X86_64, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
        BPF_JUMP(BPF_JMP | BPF_JSET | BPF_K, 0x40000000U, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_execve, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_execveat, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW)
    };
    struct sock_fprog program = { (unsigned short)(sizeof filter / sizeof filter[0]), filter };
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0)
        return -1;
    return prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program);
}

static void quoted(const char *text)
{
    putchar('"');
    for (const unsigned char *p = (const unsigned char *)text; *p; ++p) {
        if (*p == '"' || *p == '\\')
            printf("\\%c", *p);
        else if (*p < 32 || *p >= 127)
            printf("\\u%04x", (unsigned int)*p);
        else
            putchar(*p);
    }
    putchar('"');
}

static int read_record(const char *path)
{
    char buffer[65537];
    int fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0)
        return -1;
    size_t length = 0;
    while (length < sizeof buffer - 1) {
        ssize_t count = read(fd, buffer + length, sizeof buffer - 1 - length);
        if (count < 0) {
            close(fd);
            return -1;
        }
        if (count == 0)
            break;
        length += (size_t)count;
    }
    char extra;
    ssize_t remaining = read(fd, &extra, 1);
    int closed = close(fd);
    if (remaining != 0 || closed != 0)
        return -1;
    buffer[length] = '\0';
    quoted(buffer);
    return 0;
}

static int namespaces(void)
{
    const char *names[] = { "user", "mnt", "pid", "ipc", "net", "uts", "cgroup" };
    putchar('{');
    for (size_t i = 0; i < sizeof names / sizeof names[0]; ++i) {
        char path[80], target[128];
        int n = snprintf(path, sizeof path, "/proc/self/ns/%s", names[i]);
        if (n < 0 || (size_t)n >= sizeof path)
            return -1;
        ssize_t length = readlink(path, target, sizeof target - 1);
        if (length < 0 || (size_t)length >= sizeof target - 1)
            return -1;
        target[length] = '\0';
        if (i)
            putchar(',');
        quoted(names[i]);
        putchar(':');
        quoted(target);
    }
    putchar('}');
    return 0;
}

static int descriptors(void)
{
    DIR *directory = opendir("/proc/self/fd");
    if (!directory)
        return -1;
    struct dirent *entry;
    int comma = 0;
    putchar('[');
    errno = 0;
    while ((entry = readdir(directory))) {
        char *end = NULL;
        long number = strtol(entry->d_name, &end, 10);
        if (!end || *end || end == entry->d_name)
            continue;
        if (number < 0 || number > INT_MAX) {
            closedir(directory);
            return -1;
        }
        if (number == dirfd(directory))
            continue;
        struct stat info;
        int flags = fcntl((int)number, F_GETFD);
        if (flags < 0 || fstat((int)number, &info) != 0) {
            closedir(directory);
            return -1;
        }
        if (comma++)
            putchar(',');
        printf("{\"fd\":%ld,\"mode\":%u,\"dev\":%llu,\"ino\":%llu,\"cloexec\":%d}",
               number, (unsigned int)info.st_mode, (unsigned long long)info.st_dev,
               (unsigned long long)info.st_ino, !!(flags & FD_CLOEXEC));
        errno = 0;
    }
    int error = errno;
    putchar(']');
    return closedir(directory) == 0 && error == 0 ? 0 : -1;
}

static int failure_errno(long result)
{
    return result == -1 ? errno : 0;
}

static int denials(void)
{
    errno = 0;
    int fd = (int)syscall(SYS_socket, AF_UNIX, SOCK_STREAM, 0);
    int socket_error = failure_errno(fd);
    if (fd >= 0)
        close(fd); /* No connection or endpoint is ever attempted. */
    errno = 0;
    /* Invalid clone3 arguments cannot create a process even without a filter. */
    int clone_error = failure_errno(syscall(SYS_clone3, NULL, 0));
    errno = 0;
    int namespace_error = failure_errno(syscall(SYS_unshare, 0));
    errno = 0;
    /* Invalid pid: no attach to or access of an existing process, even if unfiltered. */
    int ptrace_error = failure_errno(syscall(SYS_ptrace, PTRACE_PEEKDATA, -1, NULL, NULL));
    errno = 0;
    /* Invalid null arguments cannot mount anything in an unfiltered process. */
    int mount_error = failure_errno(syscall(SYS_mount, NULL, NULL, NULL, 0, NULL));
    errno = 0;
    int uring_error = failure_errno(syscall(SYS_io_uring_setup, 0, NULL));
    errno = 0;
    char *args[] = { "/inputs/absent-helper", NULL };
    char *empty_env[] = { NULL };
    int exec_error = failure_errno(syscall(SYS_execve, args[0], args, empty_env));
    printf("{\"socket\":%d,\"clone\":%d,\"unshare\":%d,\"ptrace\":%d,"
           "\"mount\":%d,\"execve\":%d,\"io_uring_setup\":%d}",
           socket_error, clone_error, namespace_error, ptrace_error, mount_error, exec_error, uring_error);
    return 0;
}

static int sentinels(void)
{
    char bytes[64];
    int fd = open("/inputs/readonly-sentinel", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0)
        return -1;
    ssize_t length = read(fd, bytes, sizeof bytes);
    if (close(fd) != 0 || length != 20 || memcmp(bytes, "panda-inert-sentinel", 20) != 0)
        return -1;
    errno = 0;
    fd = open("/inputs/readonly-sentinel", O_WRONLY | O_CLOEXEC | O_NOFOLLOW);
    int readonly_error = failure_errno(fd);
    if (fd >= 0)
        close(fd); /* Never modify it even if the boundary is faulty. */
    errno = 0;
    fd = open("/unexposed/sentinel", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    int hidden_error = failure_errno(fd);
    if (fd >= 0)
        close(fd);
    fd = open("/out/sentinel", O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (fd < 0)
        return -1;
    ssize_t count = write(fd, "panda-inert-output", 17);
    int synced = fsync(fd);
    int closed = close(fd);
    if (count != 17 || synced != 0 || closed != 0)
        return -1;
    printf("{\"readonly_errno\":%d,\"hidden_errno\":%d,\"output_bytes\":17}",
           readonly_error, hidden_error);
    return 0;
}

static int limits(void)
{
    const int ids[] = { RLIMIT_CPU, RLIMIT_AS, RLIMIT_FSIZE, RLIMIT_NOFILE, RLIMIT_NPROC, RLIMIT_CORE };
    const char *names[] = { "cpu", "address_space", "file_size", "open_files", "processes", "core" };
    putchar('{');
    for (size_t i = 0; i < sizeof ids / sizeof ids[0]; ++i) {
        struct rlimit value;
        if (getrlimit(ids[i], &value) != 0)
            return -1;
        if (i)
            putchar(',');
        quoted(names[i]);
        printf(":[%llu,%llu]", (unsigned long long)value.rlim_cur, (unsigned long long)value.rlim_max);
    }
    putchar('}');
    return 0;
}

extern char **environ;

int main(int argc, char **argv)
{
    (void)argv;
    /* First main operation: close re-exec, including loader/libc, after loading.
     * This cannot retroactively contain the loader or libc constructors. */
    if (no_exec() != 0 || prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) != 0 || argc != 1)
        return 90;
    struct rlimit core = { 0, 0 };
    if (setrlimit(RLIMIT_CORE, &core) != 0)
        return 91;
    printf("{\"schema_version\":1,\"pid\":%ld,\"ppid\":%ld,\"namespaces\":", (long)getpid(), (long)getppid());
    if (namespaces() != 0)
        return 92;
    char proc_pid_namespace[128];
    ssize_t proc_length = readlink("/proc/1/ns/pid", proc_pid_namespace, sizeof proc_pid_namespace - 1);
    if (proc_length < 0 || (size_t)proc_length >= sizeof proc_pid_namespace - 1)
        return 92;
    proc_pid_namespace[proc_length] = '\0';
    printf(",\"proc_pid_namespace\":");
    quoted(proc_pid_namespace);
    printf(",\"mountinfo\":");
    if (read_record("/proc/self/mountinfo") != 0)
        return 93;
    printf(",\"status\":");
    if (read_record("/proc/self/status") != 0)
        return 94;
    printf(",\"fds\":");
    if (descriptors() != 0)
        return 95;
    printf(",\"environment\":[");
    for (size_t i = 0; environ[i]; ++i) {
        if (i)
            putchar(',');
        quoted(environ[i]);
    }
    printf("],\"dumpable\":%d,\"no_new_privs\":%d,\"seccomp_mode\":%d,\"denials\":",
           prctl(PR_GET_DUMPABLE, 0, 0, 0, 0), prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0),
           prctl(PR_GET_SECCOMP, 0, 0, 0, 0));
    if (denials() != 0)
        return 96;
    printf(",\"sentinels\":");
    if (sentinels() != 0)
        return 97;
    printf(",\"limits\":");
    if (limits() != 0)
        return 98;
    puts("}");
    return fflush(stdout) == 0 && !ferror(stdout) ? 0 : 99;
    /* libc exit/static teardown remains in the external lifetime trace. */
}
