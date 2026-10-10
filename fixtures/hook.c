#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <unistd.h>

/* Controlled single-thread fixtures, not general-purpose interposition. */
static int needs_mode(int flags) {
    if (flags & O_CREAT) return 1;
#ifdef O_TMPFILE
    if ((flags & O_TMPFILE) == O_TMPFILE) return 1;
#endif
    return 0;
}

#define WRAPPER(NAME) \
int NAME(const char *path, int flags, ...) { \
    int incoming_errno = errno; \
    mode_t mode = 0; \
    int with_mode = needs_mode(flags); \
    if (with_mode) { \
        va_list args; va_start(args, flags); \
        mode = va_arg(args, mode_t); va_end(args); \
    } \
    dlerror(); \
    int (*original)(const char *, int, ...) = dlsym(RTLD_NEXT, #NAME); \
    const char *error = dlerror(); \
    if (error || !original) { \
        static const char failure[] = "[HOOK] original resolution failed\n"; \
        (void)write(STDERR_FILENO, failure, sizeof(failure) - 1); \
        errno = ENOSYS; return -1; \
    } \
    errno = incoming_errno; \
    int result = with_mode ? original(path, flags, mode) : original(path, flags); \
    int saved_errno = errno; \
    static const char marker[] = "[HOOK] " #NAME " intercepted\n"; \
    (void)write(STDERR_FILENO, marker, sizeof(marker) - 1); \
    errno = saved_errno; \
    return result; \
}

WRAPPER(open)
#ifdef WITH_OPEN64
WRAPPER(open64)
#endif
