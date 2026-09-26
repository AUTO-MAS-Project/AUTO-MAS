/*
 * avdshim: a stand-in for MuMu's external_renderer_ipc.dll that serves frames from the
 * official Android Emulator (AVD) instead of a MuMu VM.
 *
 * MaaCore's MuMu screencap path loads <mumu_path>/shell/sdk/external_renderer_ipc.dll and calls
 * nemu_connect / nemu_get_display_id / nemu_capture_display / nemu_disconnect by name.
 * Point MAA's MuMu path at a directory holding this DLL and frames come from the AVD's
 * WebRTC shared memory "SHM_videmulator<console port>" (enabled by the console command
 * `screenrecord webrtc start`; layout: u32 width, height, fps, frameNumber; u64 tsUs; BGRA rows
 * top-down). MaaCore expects RGBA rows bottom-up, so capture converts while copying.
 *
 * Instance mapping for nemu_connect(path, index):
 *   index >= 5554  -> index is the emulator console port
 *   otherwise      -> index is the native index, console port = 20000 + 10 * index
 * Input functions are deliberately not exported: MaaCore then keeps adb/minitouch for input.
 *
 * Build: see build.ps1 (MinGW-w64 gcc, static libgcc, links ws2_32). The built DLL is committed next to\n * this file; AUTO-MAS copies it into <root>\\mumu-shim\\shell\\sdk\\ for every official-emulator install.
 */

#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <windows.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>

#define EXPORT __declspec(dllexport)
#define MAX_SLOTS 16
#define HEADER_SIZE 24
#define DEFAULT_PORT_BASE 20000
#define PORT_STEP 10

typedef struct {
    uint32_t width;
    uint32_t height;
    uint32_t fps;
    uint32_t frameNumber;
    uint64_t tsUs;
} VideoInfo;

typedef struct {
    int used;
    int port;
    HANDLE mapping;
    uint8_t* view;
    size_t size;
} Slot;

static Slot g_slots[MAX_SLOTS];
static CRITICAL_SECTION g_lock;
static wchar_t g_log_path[MAX_PATH];

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID reserved)
{
    (void)inst;
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        InitializeCriticalSection(&g_lock);
    }
    return TRUE;
}

static void shim_log(const char* fmt, ...)
{
    if (!g_log_path[0]) {
        return;
    }
    FILE* f = _wfopen(g_log_path, L"a");
    if (!f) {
        return;
    }
    SYSTEMTIME st;
    GetLocalTime(&st);
    fprintf(f, "%04d-%02d-%02d %02d:%02d:%02d.%03d ", st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute,
            st.wSecond, st.wMilliseconds);
    va_list ap;
    va_start(ap, fmt);
    vfprintf(f, fmt, ap);
    va_end(ap);
    fputc('\n', f);
    fclose(f);
}

/* Read from the console socket until a line "OK" or "KO..." arrives. Returns 1 on OK. */
static int console_read_until_ok(SOCKET s, char* buf, int cap)
{
    int len = 0;
    for (;;) {
        int n = recv(s, buf + len, cap - 1 - len, 0);
        if (n <= 0) {
            return 0;
        }
        len += n;
        buf[len] = '\0';
        if (strstr(buf, "\nOK") || strncmp(buf, "OK", 2) == 0) {
            return 1;
        }
        if (strstr(buf, "KO")) {
            return 0;
        }
        if (len >= cap - 1) {
            return 0;
        }
    }
}

/* Ask the emulator console to enable the WebRTC shared-memory video bridge. */
static int console_webrtc_start(int port)
{
    char token[256] = { 0 };
    wchar_t token_path[MAX_PATH];
    DWORD n = GetEnvironmentVariableW(L"USERPROFILE", token_path, MAX_PATH);
    if (n > 0 && n < MAX_PATH - 40) {
        wcscat(token_path, L"\\.emulator_console_auth_token");
        FILE* f = _wfopen(token_path, L"rb");
        if (f) {
            size_t r = fread(token, 1, sizeof(token) - 1, f);
            fclose(f);
            token[r] = '\0';
            for (size_t i = 0; i < r; ++i) {
                if (token[i] == '\r' || token[i] == '\n') {
                    token[i] = '\0';
                    break;
                }
            }
        }
    }

    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
        return 0;
    }
    int ok = 0;
    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s != INVALID_SOCKET) {
        DWORD timeout_ms = 3000;
        setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, (const char*)&timeout_ms, sizeof(timeout_ms));
        struct sockaddr_in addr;
        memset(&addr, 0, sizeof(addr));
        addr.sin_family = AF_INET;
        addr.sin_port = htons((u_short)port);
        addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        char buf[4096];
        char cmd[512];
        if (connect(s, (struct sockaddr*)&addr, sizeof(addr)) == 0 && console_read_until_ok(s, buf, sizeof(buf))) {
            int authed = 1;
            if (token[0]) {
                snprintf(cmd, sizeof(cmd), "auth %s\r\n", token);
                send(s, cmd, (int)strlen(cmd), 0);
                authed = console_read_until_ok(s, buf, sizeof(buf));
            }
            if (authed) {
                const char* start = "screenrecord webrtc start\r\n";
                send(s, start, (int)strlen(start), 0);
                ok = console_read_until_ok(s, buf, sizeof(buf));
                shim_log("console %d webrtc start -> %s", port, ok ? "OK" : "fail");
            }
            else {
                shim_log("console %d auth failed", port);
            }
            send(s, "quit\r\n", 6, 0);
        }
        else {
            shim_log("console %d connect failed (%d)", port, WSAGetLastError());
        }
        closesocket(s);
    }
    WSACleanup();
    return ok;
}

static int open_shm(Slot* slot)
{
    wchar_t name[64];
    swprintf(name, 64, L"SHM_videmulator%d", slot->port);
    HANDLE h = OpenFileMappingW(FILE_MAP_READ, FALSE, name);
    if (!h) {
        return 0;
    }
    uint8_t* view = (uint8_t*)MapViewOfFile(h, FILE_MAP_READ, 0, 0, 0);
    if (!view) {
        CloseHandle(h);
        return 0;
    }
    MEMORY_BASIC_INFORMATION mbi;
    VirtualQuery(view, &mbi, sizeof(mbi));
    slot->mapping = h;
    slot->view = view;
    slot->size = mbi.RegionSize;
    return 1;
}

static Slot* get_slot(int handle)
{
    if (handle < 1 || handle > MAX_SLOTS) {
        return NULL;
    }
    Slot* s = &g_slots[handle - 1];
    return s->used ? s : NULL;
}

EXPORT int nemu_connect(const wchar_t* path, int index)
{
    if (path && path[0] && wcslen(path) < MAX_PATH - 16) {
        wcscpy(g_log_path, path);
        wcscat(g_log_path, L"\\avdshim.log");
    }
    int port = index >= 5554 ? index : DEFAULT_PORT_BASE + PORT_STEP * index;

    EnterCriticalSection(&g_lock);
    int handle = 0;
    for (int i = 0; i < MAX_SLOTS; ++i) {
        if (!g_slots[i].used) {
            handle = i + 1;
            break;
        }
    }
    LeaveCriticalSection(&g_lock);
    if (!handle) {
        shim_log("connect index=%d: no free slot", index);
        return 0;
    }

    Slot slot = { 0 };
    slot.port = port;
    if (!open_shm(&slot)) {
        console_webrtc_start(port);
        for (int i = 0; i < 40 && !open_shm(&slot); ++i) {
            Sleep(50);
        }
    }
    if (!slot.view) {
        shim_log("connect index=%d port=%d: shared memory unavailable", index, port);
        return 0;
    }
    const VideoInfo* vi = (const VideoInfo*)slot.view;
    shim_log("connect index=%d port=%d handle=%d %ux%u fps=%u frame=%u size=%zu", index, port, handle, vi->width,
             vi->height, vi->fps, vi->frameNumber, slot.size);

    EnterCriticalSection(&g_lock);
    slot.used = 1;
    g_slots[handle - 1] = slot;
    LeaveCriticalSection(&g_lock);
    return handle;
}

EXPORT void nemu_disconnect(int handle)
{
    EnterCriticalSection(&g_lock);
    Slot* s = get_slot(handle);
    if (s) {
        UnmapViewOfFile(s->view);
        CloseHandle(s->mapping);
        shim_log("disconnect handle=%d port=%d", handle, s->port);
        memset(s, 0, sizeof(*s));
    }
    LeaveCriticalSection(&g_lock);
}

EXPORT int nemu_get_display_id(int handle, const char* pkg, int app_index)
{
    (void)pkg;
    (void)app_index;
    return get_slot(handle) ? 0 : -1;
}

/* Returns 0 on success (MuMu convention). With buffer_size 0 / pixels NULL only reports the size. */
EXPORT int nemu_capture_display(int handle, unsigned int display_id, int buffer_size, int* width, int* height,
                                unsigned char* pixels)
{
    (void)display_id;
    Slot* s = get_slot(handle);
    if (!s) {
        return -1;
    }
    const volatile VideoInfo* vi = (const volatile VideoInfo*)s->view;
    uint32_t w = vi->width;
    uint32_t h = vi->height;
    size_t frame_bytes = (size_t)w * h * 4;
    if (w == 0 || h == 0 || HEADER_SIZE + frame_bytes > s->size) {
        return -2;
    }
    if (width) {
        *width = (int)w;
    }
    if (height) {
        *height = (int)h;
    }
    if (buffer_size == 0 || !pixels) {
        return 0;
    }
    if ((size_t)buffer_size < frame_bytes) {
        return -3;
    }

    const uint32_t* src = (const uint32_t*)(s->view + HEADER_SIZE);
    uint32_t* dst = (uint32_t*)pixels;
    /* Retry if the emulator published a new frame mid-copy, to avoid a torn image. */
    for (int attempt = 0; attempt < 3; ++attempt) {
        uint32_t before = vi->frameNumber;
        for (uint32_t y = 0; y < h; ++y) {
            const uint32_t* sr = src + (size_t)(h - 1 - y) * w;
            uint32_t* dr = dst + (size_t)y * w;
            for (uint32_t x = 0; x < w; ++x) {
                uint32_t p = sr[x]; /* bytes B,G,R,A -> R,G,B,A */
                dr[x] = (p & 0xFF00FF00u) | ((p & 0xFFu) << 16) | ((p >> 16) & 0xFFu);
            }
        }
        if (vi->frameNumber == before) {
            break;
        }
    }
    return 0;
}
