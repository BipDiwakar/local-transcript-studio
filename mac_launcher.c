#include <limits.h>
#include <libgen.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char *argv[]) {
    char executable_path[PATH_MAX];
    char app_path[PATH_MAX];
    char script_path[PATH_MAX];
    char *bundle_marker;

    if (realpath(argv[0], executable_path) == NULL) {
        return 1;
    }

    strncpy(app_path, executable_path, sizeof(app_path) - 1);
    app_path[sizeof(app_path) - 1] = '\0';
    bundle_marker = strstr(app_path, ".app/Contents/MacOS/");
    if (bundle_marker == NULL) {
        return 1;
    }
    bundle_marker[4] = '\0';

    snprintf(script_path, sizeof(script_path), "%s/Contents/Resources/launch_app.command", app_path);
    chdir(app_path);
    execl("/bin/zsh", "zsh", script_path, (char *)NULL);
    return 1;
}
