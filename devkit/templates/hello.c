/* MIT. A small Android ARM64 wl_shm app for the local DevKit guest. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <stdlib.h>
#include <sys/mman.h>
struct wl_proxy; struct wl_display; struct wl_interface;
extern const struct wl_interface wl_registry_interface, wl_compositor_interface;
extern const struct wl_interface wl_shell_interface, wl_shell_surface_interface;
extern const struct wl_interface wl_surface_interface, wl_shm_interface;
extern const struct wl_interface wl_shm_pool_interface, wl_buffer_interface;
extern struct wl_display *wl_display_connect(const char *);
extern int wl_display_roundtrip(struct wl_display *);
extern int wl_display_dispatch(struct wl_display *);
extern int wl_display_flush(struct wl_display *);
extern void wl_display_disconnect(struct wl_display *);
extern void wl_proxy_marshal(struct wl_proxy *, uint32_t, ...);
extern struct wl_proxy *wl_proxy_marshal_constructor(struct wl_proxy *, uint32_t, const struct wl_interface *, ...);
extern struct wl_proxy *wl_proxy_marshal_constructor_versioned(struct wl_proxy *, uint32_t, const struct wl_interface *, uint32_t, ...);
extern int wl_proxy_add_listener(struct wl_proxy *, void (**)(void), void *);
static struct wl_proxy *compositor, *shell, *shm;
static void added(void *data, struct wl_proxy *registry, uint32_t id, const char *name, uint32_t version) {
    (void)data; (void)version;
    const struct wl_interface *interface = NULL; struct wl_proxy **out = NULL;
    if (!strcmp(name,"wl_compositor")) {interface=&wl_compositor_interface;out=&compositor;}
    if (!strcmp(name,"wl_shell")) {interface=&wl_shell_interface;out=&shell;}
    if (!strcmp(name,"wl_shm")) {interface=&wl_shm_interface;out=&shm;}
    if (out) *out=wl_proxy_marshal_constructor_versioned(registry,0,interface,1,id,name,1,NULL);
}
static void removed(void *data, struct wl_proxy *r, uint32_t id) {(void)data;(void)r;(void)id;}
static void ping(void *data, struct wl_proxy *surface, uint32_t serial) {(void)data;wl_proxy_marshal(surface,0,serial);}
static void configure(void *data, void *s, uint32_t edges, int32_t w, int32_t h) {(void)data;(void)s;(void)edges;(void)w;(void)h;}
static void popup(void *data, void *s) {(void)data;(void)s;}
static void format(void *data, void *s, uint32_t f) {(void)data;(void)s;(void)f;}
static void released(void *data, void *b) {(void)data;(void)b;}
/* 5x7 bitmap font for the example title; no firmware artwork is included. */
static const unsigned char glyphs[7][7] = {
    {17,17,17,31,17,17,17}, {31,16,16,30,16,16,31},
    {16,16,16,16,16,16,31}, {14,17,17,17,17,17,14},
    {17,17,10,4,10,17,17}, {14,17,1,2,4,8,31},
    {30,17,17,17,17,17,30}
};
static void title(uint32_t *pixels, const char *text, int x, int y) {
    const char *alphabet="HELOX2D";
    for (;*text;++text,x+=60) {
        const char *g=strchr(alphabet,*text); if (!g) continue;
        for (int row=0;row<7;row++) for (int col=0;col<5;col++)
            if (glyphs[g-alphabet][row] & (1<<(4-col)))
                for (int dy=0;dy<8;dy++) for (int dx=0;dx<8;dx++)
                    pixels[(y+row*8+dy)*1024+x+col*8+dx]=0xffeaddff;
    }
}
int main(void) {
    struct wl_display *display=wl_display_connect(NULL); if (!display) {perror("Wayland");return 1;}
    struct wl_proxy *registry=wl_proxy_marshal_constructor((struct wl_proxy *)display,1,&wl_registry_interface,NULL);
    void (*registry_events[])(void)={(void(*)(void))added,(void(*)(void))removed};
    wl_proxy_add_listener(registry,registry_events,NULL); wl_display_roundtrip(display);
    if (!compositor || !shell || !shm) {fputs("Missing compositor globals\n",stderr);return 2;}
    void (*shm_events[])(void)={(void(*)(void))format}; wl_proxy_add_listener(shm,shm_events,NULL);
    const size_t bytes=1024*768*4;
    char path[]="/dev/devkit-shm-XXXXXX"; int fd=mkstemp(path);
    if (fd<0 || ftruncate(fd,bytes)) return 3;
    unlink(path);
    uint32_t *pixels=mmap(NULL,bytes,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0); if(pixels==MAP_FAILED)return 4;
    for (int y=0;y<768;y++) for(int x=0;x<1024;x++)
        pixels[y*1024+x]=(x>60 && x<964 && y>80 && y<688)?0xff211f26:0xff141218;
    for(int y=510;y<518;y++)for(int x=150;x<874;x++)pixels[y*1024+x]=0xffd0bcff;
    title(pixels,"HELLO X2D",245,340);
    struct wl_proxy *pool=wl_proxy_marshal_constructor(shm,0,&wl_shm_pool_interface,NULL,fd,(int)bytes);
    struct wl_proxy *buffer=wl_proxy_marshal_constructor(pool,0,&wl_buffer_interface,NULL,0,1024,768,4096,1);
    void (*buffer_events[])(void)={(void(*)(void))released};wl_proxy_add_listener(buffer,buffer_events,NULL);
    struct wl_proxy *surface=wl_proxy_marshal_constructor(compositor,0,&wl_surface_interface,NULL);
    struct wl_proxy *ss=wl_proxy_marshal_constructor(shell,0,&wl_shell_surface_interface,NULL,surface);
    void (*shell_events[])(void)={(void(*)(void))ping,(void(*)(void))configure,(void(*)(void))popup};
    wl_proxy_add_listener(ss,shell_events,NULL); wl_proxy_marshal(ss,3);
    wl_proxy_marshal(surface,1,buffer,0,0);wl_proxy_marshal(surface,2,0,0,1024,768);wl_proxy_marshal(surface,6);
    wl_display_flush(display);puts("DEVKIT_HELLO_READY");fflush(stdout);
    while(wl_display_dispatch(display)>=0) {}
    wl_display_disconnect(display); munmap(pixels,bytes);close(fd);return 0;
}
