#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    if (strcmp(argv[1], "--skip") == 0) {
        puts("target: skipped");
        return 0;
    }
    if (strcmp(argv[1], "--call") != 0) return 2;
    int fd = open("/dev/null", O_RDONLY);
    if (fd < 0) { perror("open"); return 1; }
    if (close(fd) != 0) { perror("close"); return 1; }
    puts("target: called");
    return 0;
}
