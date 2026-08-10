// Two small C probes for XWayland/XI2 input under a Wayland compositor.
// Compile with the recipe in SKILL.md (nixpkgs .dev include dirs), then either
//
//   GRAB:  ./probe-grab            -> prints GRAB_FREE or ALREADY_GRABBED
//   RAW:   ./probe-xi              -> subscribes XI_RawMotion on the ROOT and
//                                     prints deltas exactly as GLFW reads them
//                                     (re->raw_values). Set PROBE_WIN=0x... to
//                                     select a specific window instead of root.
//
// Both are read-only; they never warp or move the real cursor.

// ============================ probe-grab.c ============================
// Does anything currently hold the X pointer grab? Run in a loop with
// timestamps to correlate with what the user is doing.
/*
#include <X11/Xlib.h>
#include <stdio.h>

int main(void) {
    Display *d = XOpenDisplay(NULL);
    if (!d) { fprintf(stderr, "open failed\n"); return 1; }
    int rc = XGrabPointer(d, DefaultRootWindow(d), False, 0,
                          GrabModeAsync, GrabModeAsync, None, None, CurrentTime);
    if (rc == GrabSuccess) {
        printf("GRAB_FREE\n");
        XUngrabPointer(d, CurrentTime);
    } else if (rc == AlreadyGrabbed) {
        printf("ALREADY_GRABBED\n");
    } else {
        printf("rc=%d\n", rc);
    }
    XSync(d, False);
    XCloseDisplay(d);
    return 0;
}
*/

// ============================ probe-xi.c ============================
// Subscribe XI_RawMotion|XI_Motion on the ROOT (exactly what GLFW/LWJGL do),
// print raw_values so you can see if relative motion reaches the X server.
/*
#include <X11/Xlib.h>
#include <X11/extensions/XInput2.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

int main(void) {
    Display *dpy = XOpenDisplay(NULL);
    if (!dpy) { fprintf(stderr, "open failed\n"); return 1; }
    Window target = 0;
    const char *arg = getenv("PROBE_WIN");
    if (arg) target = (Window)strtoul(arg, NULL, 0);
    if (!target) target = DefaultRootWindow(dpy);
    fprintf(stderr, "selecting on window 0x%lx\n", target);

    int op, ev, err;
    if (!XQueryExtension(dpy, "XInputExtension", &op, &ev, &err)) return 1;
    int major = 2, minor = 0;
    if (XIQueryVersion(dpy, &major, &minor) != Success) return 1;
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
            if (xev.xcookie.type != GenericEvent || xev.xcookie.extension != op) continue;
            if (!XGetEventData(dpy, &xev.xcookie)) continue;
            int type = xev.xcookie.evtype;
            if (type == XI_RawMotion) {
                XIRawEvent *re = (XIRawEvent *)xev.xcookie.data;
                raw_events++;
                if (raw_events <= 5) {
                    printf("RAW dev=%d source=%d: ", re->deviceid, re->sourceid);
                    int vi = 0;
                    for (int i = 0; i < re->valuators.mask_len * 8; i++)
                        if (XIMaskIsSet(re->valuators.mask, i)) {
                            printf("v%d(%.2f acm/%.2f) ", i,
                                   re->valuators.values[vi], re->raw_values[vi]);
                            vi++;
                        }
                    printf("\n");
                }
            } else if (type == XI_Motion) {
                motion_events++;
            }
            XFreeEventData(dpy, &xev.xcookie);
        }
    }
    printf("TOTAL raw=%d motion=%d\n", raw_events, motion_events);
    XCloseDisplay(dpy);
    return 0;
}
*/