CC = cc
.PHONY: all static clean
all: app_normal app_large libhook_open.so libhook_fixed.so app_conditional_now libhook_no_export.so
app_normal: app.c
	$(CC) -O2 app.c -o $@
app_large: app.c
	$(CC) -O2 -D_FILE_OFFSET_BITS=64 app.c -o $@
libhook_open.so: hook.c
	$(CC) -shared -fPIC hook.c -o $@ -ldl
libhook_fixed.so: hook.c
	$(CC) -shared -fPIC -DWITH_OPEN64 hook.c -o $@ -ldl
app_conditional_now: app_conditional.c
	$(CC) -O2 -D_FILE_OFFSET_BITS=64 app_conditional.c -Wl,-z,now -o $@
libhook_no_export.so: hook_no_export.c
	$(CC) -shared -fPIC hook_no_export.c -o $@
static:
	$(CC) -O2 -static app.c -o app_static
clean:
	rm -f app_normal app_large app_conditional_now app_static libhook_open.so libhook_fixed.so libhook_no_export.so
