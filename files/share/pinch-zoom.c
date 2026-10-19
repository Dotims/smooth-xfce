// Touchpad pinch -> smooth Ctrl+wheel for Chrome on X11 (Chrome ignores XI 2.4 gestures).
// Build: gcc -O2 -o ~/.local/bin/pinch-zoom pinch-zoom.c -lX11 -lXi -lm
// Usage: pinch-zoom [gain]   gain = hi-res wheel units (120 = one notch) per ln(scale)
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/extensions/XInput2.h>
#include <fcntl.h>
#include <linux/uinput.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/ioctl.h>
#include <unistd.h>

static const char *apps[] = {"Google-chrome", "Chromium", NULL};
static int ufd = -1;

static void emit(int type, int code, int value) {
    struct input_event ev = {0};
    ev.type = type;
    ev.code = code;
    ev.value = value;
    if (write(ufd, &ev, sizeof ev) < 0) perror("pinch-zoom: write");
}

static void syn(void) { emit(EV_SYN, SYN_REPORT, 0); }

static int open_uinput(void) {
    int fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK);
    if (fd < 0) return -1;
    // REL_X/REL_Y + BTN_LEFT so udev/libinput tag it as a mouse; never emitted
    ioctl(fd, UI_SET_EVBIT, EV_KEY);
    ioctl(fd, UI_SET_KEYBIT, KEY_LEFTCTRL);
    ioctl(fd, UI_SET_KEYBIT, BTN_LEFT);
    ioctl(fd, UI_SET_EVBIT, EV_REL);
    ioctl(fd, UI_SET_RELBIT, REL_X);
    ioctl(fd, UI_SET_RELBIT, REL_Y);
    ioctl(fd, UI_SET_RELBIT, REL_WHEEL);
    ioctl(fd, UI_SET_RELBIT, REL_WHEEL_HI_RES);
    struct uinput_setup us = {0};
    us.id.bustype = BUS_VIRTUAL;
    strcpy(us.name, "pinch-zoom");
    if (ioctl(fd, UI_DEV_SETUP, &us) < 0 || ioctl(fd, UI_DEV_CREATE) < 0) {
        close(fd);
        return -1;
    }
    return fd;
}

// The child of root is the WM frame; WM_CLASS sits on the client window below it
static int is_target(Display *d, Window w, int depth) {
    if (w == None) return 0;
    XClassHint ch;
    if (XGetClassHint(d, w, &ch)) {
        int hit = 0;
        for (const char **a = apps; *a; a++)
            if (ch.res_class && !strcasecmp(ch.res_class, *a)) hit = 1;
        XFree(ch.res_name);
        XFree(ch.res_class);
        return hit;
    }
    if (depth == 0) return 0;
    Window root, parent, *kids = NULL;
    unsigned n = 0;
    int hit = 0;
    if (XQueryTree(d, w, &root, &parent, &kids, &n)) {
        for (unsigned i = 0; i < n && !hit; i++) hit = is_target(d, kids[i], depth - 1);
        if (kids) XFree(kids);
    }
    return hit;
}

int main(int argc, char **argv) {
    double gain = argc > 1 ? atof(argv[1]) : 300;

    Display *d = XOpenDisplay(NULL);
    if (!d) { fprintf(stderr, "pinch-zoom: no display\n"); return 1; }
    int opcode, ev, err, major = 2, minor = 4;
    if (!XQueryExtension(d, "XInputExtension", &opcode, &ev, &err) ||
        XIQueryVersion(d, &major, &minor) != Success || major * 10 + minor < 24) {
        fprintf(stderr, "pinch-zoom: XInput 2.4 not available\n");
        return 1;
    }
    ufd = open_uinput();
    if (ufd < 0) { perror("pinch-zoom: /dev/uinput"); return 1; }

    unsigned char bits[XIMaskLen(XI_LASTEVENT)] = {0};
    XISetMask(bits, XI_GesturePinchBegin);
    XISetMask(bits, XI_GesturePinchUpdate);
    XISetMask(bits, XI_GesturePinchEnd);
    XIEventMask mask = {XIAllMasterDevices, sizeof bits, bits};
    XISelectEvents(d, DefaultRootWindow(d), &mask, 1);
    XFlush(d);

    int active = 0, notch = 0;
    double last = 1, acc = 0;
    for (;;) {
        XEvent e;
        XNextEvent(d, &e);
        XGenericEventCookie *c = &e.xcookie;
        if (c->type != GenericEvent || c->extension != opcode || !XGetEventData(d, c)) continue;
        XIGesturePinchEvent *p = c->data;
        switch (c->evtype) {
        case XI_GesturePinchBegin:
            active = is_target(d, p->child, 2);
            if (getenv("PINCH_ZOOM_DEBUG"))
                fprintf(stderr, "begin child=0x%lx target=%d\n", p->child, active);
            last = p->scale > 0 ? p->scale : 1;
            acc = 0;
            notch = 0;
            if (active) { emit(EV_KEY, KEY_LEFTCTRL, 1); syn(); }
            break;
        case XI_GesturePinchUpdate:
            if (!active || p->scale <= 0) break;
            acc += log(p->scale / last) * gain;
            last = p->scale;
            int v = (int)acc;
            if (v) {
                acc -= v;
                // Touchpad gesture events switch the master pointer away and Chrome
                // drops the first scroll after each switch, so send a 1-unit primer
                int primer = v > 0 ? 1 : -1;
                emit(EV_REL, REL_WHEEL_HI_RES, primer);
                syn();
                emit(EV_REL, REL_WHEEL_HI_RES, v);
                // Legacy clicks alongside hi-res, as real wheels do
                notch += v + primer;
                while (notch >= 120) { emit(EV_REL, REL_WHEEL, 1); notch -= 120; }
                while (notch <= -120) { emit(EV_REL, REL_WHEEL, -1); notch += 120; }
                syn();
            }
            break;
        case XI_GesturePinchEnd:
            if (active) { emit(EV_KEY, KEY_LEFTCTRL, 0); syn(); }
            active = 0;
            break;
        }
        XFreeEventData(d, c);
    }
}
