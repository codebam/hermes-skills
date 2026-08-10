// X pointer-grab state probe: is the pointer currently grabbed by any client?
// Prints "GRAB_FREE (probe grabbed it)" when nobody holds the grab (probe takes
// and instantly releases it), or "ALREADY_GRABBED" when a client holds it.
//
// Useful to confirm whether a game's capture (GLFW CURSOR_DISABLED / XGrabPointer)
// is active at a given moment. Poll it in a loop with a timestamp while the user
// reproduces, and correlate with when they are actually in-game.
//
// Build:
//   cc grabprobe.c -o grabprobe -lX11
// Run:
//   DISPLAY=:0 ./grabprobe
#include <X11/Xlib.h>
#include <stdio.h>

int main(void) {
    Display *dpy = XOpenDisplay(NULL);
    if (!dpy) { printf("open failed\n"); return 1; }
    int rc = XGrabPointer(dpy, DefaultRootWindow(dpy), False, 0,
                          GrabModeAsync, GrabModeAsync, None, None, CurrentTime);
    if (rc == GrabSuccess) {
        printf("GRAB_FREE (probe grabbed it)\n");
        XUngrabPointer(dpy, CurrentTime);
    } else if (rc == AlreadyGrabbed) {
        printf("ALREADY_GRABBED\n");
    } else {
        printf("rc=%d\n", rc);
    }
    XSync(dpy, False);
    XCloseDisplay(dpy);
    return 0;
}