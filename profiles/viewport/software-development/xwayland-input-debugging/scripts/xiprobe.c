// XI2 raw-motion + core-motion probe that mirrors how GLFW consumes mouse input
// under XWayland. Authoritative "do the deltas reach the X server?" check.
//
// GLFW 3.4 selects XI_RawMotion on the ROOT window for XIAllMasterDevices
// (src/x11_window.c: enableRawMouseMotion). This probe does the same, by default
// on the root so it matches. Point it at a specific X window with PROBE_WIN
// (e.g. PROBE_WIN=0x400007) to compare a window-level selection against root.
//
// Build (Linux, any distro):
//   cc xiprobe.c -o xiprobe -lX11 -lXi
// Run:
//   DISPLAY=:0 ./xiprobe            # ~8s of captures on the root
//   DISPLAY=:0 timeout 30 ./xiprobe # longer
//
// Interpret: nonzero re->raw_values on source=the "xwayland-relative-pointer"
// device => the compositor->XWayland->X server relative path delivers. If the
// game still doesn't move, the break is inside the client (GLFW rawMouseMotion /
// disabledCursorWindow) — it can't be seen from here.
#include <X11/Xlib.h>
#include <X11/extensions/XInput2.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>

int main(void) {
    Display *dpy = XOpenDisplay(NULL);
    if (!dpy) { printf("open failed\n"); return 1; }
    Window target = 0;
    const char *arg = getenv("PROBE_WIN");
    if (arg) target = (Window)strtoul(arg, NULL, 0);
    if (!target) target = DefaultRootWindow(dpy);
    printf("selecting on 0x%lx (%s)\n", target,
           arg ? "PROBE_WIN" : "root");

    int op, ev, err;
    if (!XQueryExtension(dpy, "XInputExtension", &op, &ev, &err)) {
        printf("no XI\n"); return 1;
    }
    int major = 2, minor = 0;
    XIQueryVersion(dpy, &major, &minor);
    printf("XI2 %d.%d\n", major, minor);

    unsigned char mask[XIMaskLen(XI_LASTEVENT)] = {0};
    XISetMask(mask, XI_RawMotion);
    XISetMask(mask, XI_Motion);
    XISelectEvents(dpy, target, (XIEventMask[]){
        { .deviceid = XIAllMasterDevices, .mask_len = sizeof(mask), .mask = mask }}, 1);
    XSync(dpy, False);

    unsigned long start = time(NULL);
    int raw_events = 0, motion_events = 0;
    while ((unsigned long)time(NULL) - start < 8) {
        while (XPending(dpy)) {
            XEvent xev;
            XNextEvent(dpy, &xev);
            if (xev.xcookie.type != GenericEvent || xev.xcookie.extension != op)
                continue;
            if (!XGetEventData(dpy, &xev.xcookie)) continue;
            int type = xev.xcookie.evtype;
            if (type == XI_RawMotion) {
                raw_events++;
                if (raw_events <= 5) {
                    XIRawEvent *re = (XIRawEvent *)xev.xcookie.data;
                    printf("RAW dev=%d source=%d", re->deviceid, re->sourceid);
                    int vi = 0;
                    for (int i = 0; i < re->valuators.mask_len * 8; i++)
                        if (XIMaskIsSet(re->valuators.mask, i)) {
                            printf(" v%d(%.2f acc/%.2f raw) ", i,
                                   re->valuators.values[vi], re->raw_values[vi]);
                            vi++;
                        }
                    printf("\n");
                }
            } else if (type == XI_Motion) {
                XIDeviceEvent *de = (XIDeviceEvent *)xev.xcookie.data;
                motion_events++;
                if (motion_events <= 3)
                    printf("MOTION dev=%d pos=%d,%d\n", de->deviceid,
                           de->event_x, de->event_y);
            }
            XFreeEventData(dpy, &xev.xcookie);
        }
        usleep(2000);
    }
    printf("TOTAL raw=%d motion=%d\n", raw_events, motion_events);
    XCloseDisplay(dpy);
    return 0;
}