#include <fcntl.h>
#include <stdio.h>
#include <unistd.h>

int main(void) {
    int fd = open("/dev/null", O_RDONLY);
    if (fd < 0) { perror("open"); return 1; }
    if (close(fd) != 0) { perror("close"); return 1; }
    puts("target: success");
    return 0;
}
