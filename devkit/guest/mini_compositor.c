/* Minimal wl_shell + wl_shm compositor for a disposable QEMU UI guest.
 * Uses the firmware's exported libwayland-server ABI in libweston.so.
 * Output is a private virtual block disk, never a physical camera device.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <time.h>
#include <sys/stat.h>
#include <errno.h>

struct wl_display; struct wl_client; struct wl_resource; struct wl_interface;
struct wl_shm_buffer; struct wl_global;
extern const struct wl_interface wl_compositor_interface, wl_surface_interface;
extern const struct wl_interface wl_region_interface, wl_shell_interface;
extern const struct wl_interface wl_shell_surface_interface, wl_callback_interface;
extern const struct wl_interface wl_output_interface, wl_subcompositor_interface;
extern const struct wl_interface wl_subsurface_interface;
extern const struct wl_interface wl_seat_interface, wl_touch_interface;
struct wl_event_loop; struct wl_event_source;
extern struct wl_event_loop *wl_display_get_event_loop(struct wl_display *);
extern struct wl_event_source *wl_event_loop_add_fd(struct wl_event_loop *, int, uint32_t,
    int (*)(int,uint32_t,void *),void *);
extern uint32_t wl_display_next_serial(struct wl_display *);
extern struct wl_display *wl_display_create(void);
extern int wl_display_add_socket(struct wl_display *, const char *);
extern int wl_display_init_shm(struct wl_display *);
extern void wl_display_run(struct wl_display *);
extern struct wl_global *wl_global_create(struct wl_display *, const struct wl_interface *,
    int, void *, void (*)(struct wl_client *, void *, uint32_t, uint32_t));
extern struct wl_resource *wl_resource_create(struct wl_client *, const struct wl_interface *, int, uint32_t);
extern void wl_resource_set_implementation(struct wl_resource *, const void *, void *, void (*)(struct wl_resource *));
extern void *wl_resource_get_user_data(struct wl_resource *);
extern int wl_resource_get_version(struct wl_resource *);
extern void wl_resource_destroy(struct wl_resource *);
extern void wl_resource_post_event(struct wl_resource *, uint32_t, ...);
extern struct wl_shm_buffer *wl_shm_buffer_get(struct wl_resource *);
extern void *wl_shm_buffer_get_data(struct wl_shm_buffer *);
extern int32_t wl_shm_buffer_get_width(struct wl_shm_buffer *);
extern int32_t wl_shm_buffer_get_height(struct wl_shm_buffer *);
extern int32_t wl_shm_buffer_get_stride(struct wl_shm_buffer *);
extern uint32_t wl_shm_buffer_get_format(struct wl_shm_buffer *);
extern void wl_shm_buffer_begin_access(struct wl_shm_buffer *);
extern void wl_shm_buffer_end_access(struct wl_shm_buffer *);

struct surface {
    struct wl_resource *buffer;
    struct wl_resource *callbacks[32];
    unsigned count;
};
static const char *output_path;
static unsigned frame_number;
static uint64_t total_frame_ms;
static int frame_fd=-1;
static struct wl_display *server;
static struct wl_resource *touch_resource, *focus_surface;
static int touch_down;
static uint64_t now_ms(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}
static void destroy(struct wl_client *c, struct wl_resource *r) {(void)c; wl_resource_destroy(r);}
static void rect(struct wl_client *c, struct wl_resource *r, int32_t x, int32_t y, int32_t w, int32_t h) {
    (void)c; (void)r; (void)x; (void)y; (void)w; (void)h;
}
static void region(struct wl_client *c, struct wl_resource *r, struct wl_resource *other) {(void)c;(void)r;(void)other;}
static void integer(struct wl_client *c, struct wl_resource *r, int32_t value) {(void)c;(void)r;(void)value;}
static void noop(struct wl_client *c, struct wl_resource *r) {(void)c;(void)r;}
static void attach(struct wl_client *c, struct wl_resource *r, struct wl_resource *b, int32_t x, int32_t y) {
    (void)c;(void)x;(void)y; ((struct surface *)wl_resource_get_user_data(r))->buffer = b;
}
static void frame(struct wl_client *c, struct wl_resource *r, uint32_t id) {
    struct surface *s = wl_resource_get_user_data(r);
    struct wl_resource *cb = wl_resource_create(c, &wl_callback_interface, 1, id);
    if (s->count < 32) s->callbacks[s->count++] = cb;
    else {wl_resource_post_event(cb, 0, (uint32_t)now_ms()); wl_resource_destroy(cb);}
}
static int write_all(int fd,const void *data,size_t bytes){
    const char *p=data;
    while(bytes){ssize_t n=write(fd,p,bytes);if(n<0 && errno==EINTR)continue;if(n<=0)return -1;p+=n;bytes-=n;}
    return 0;
}
static void write_frame(struct wl_shm_buffer *b) {
    uint64_t began=now_ms();
    int w=wl_shm_buffer_get_width(b), h=wl_shm_buffer_get_height(b), stride=wl_shm_buffer_get_stride(b);
    uint32_t format=wl_shm_buffer_get_format(b);
    if (w<=0 || h<=0 || w>4096 || h>4096 || stride<w*4 || stride>32768 || format>1) return;
    if(frame_fd>=0){
        uint32_t head[128]={0x58463244,w,h,stride,format,++frame_number};
        wl_shm_buffer_begin_access(b);
        int failed=write_all(frame_fd,head,sizeof(head));
        if(!failed)failed=write_all(frame_fd,wl_shm_buffer_get_data(b),(size_t)stride*h);
        wl_shm_buffer_end_access(b);
        if(failed){perror("frame stream");close(frame_fd);frame_fd=-1;return;}
        total_frame_ms+=now_ms()-began;
        if(frame_number==1 || frame_number%30==0){printf("CAMERA_FRAME %u %dx%d transport=virtio average_write_ms=%llu\n",frame_number,w,h,(unsigned long long)(total_frame_ms/frame_number));fflush(stdout);}
        return;
    }
    int fd=open(output_path,O_WRONLY|O_CLOEXEC);
    if(fd<0) {perror("frame output");return;}
    uint32_t header[128]={0x58463244, (uint32_t)w, (uint32_t)h, (uint32_t)stride, format, ++frame_number};
    size_t bytes=(size_t)stride*h;
    if(bytes+sizeof(header)>32*1024*1024) {close(fd);return;}
    wl_shm_buffer_begin_access(b);
    uint32_t invalid=0;
    if(pwrite(fd,&invalid,sizeof(invalid),0)==sizeof(invalid)) {
        const char *pixels=wl_shm_buffer_get_data(b); size_t offset=0;
        while(offset<bytes) {ssize_t n=pwrite(fd,pixels+offset,bytes-offset,sizeof(header)+offset);if(n<=0)break;offset+=n;}
        if(offset==bytes)pwrite(fd,header,sizeof(header),0);
        fsync(fd);
        total_frame_ms+=now_ms()-began;
        if(frame_number==1 || frame_number%30==0){
            printf("CAMERA_FRAME %u %dx%d bytes=%zu average_write_ms=%llu\n",frame_number,w,h,offset,(unsigned long long)(total_frame_ms/frame_number));fflush(stdout);
        }
    }
    wl_shm_buffer_end_access(b);close(fd);
}
static void commit(struct wl_client *c, struct wl_resource *r) {
    (void)c;struct surface *s=wl_resource_get_user_data(r);
    if(s->buffer) {
        struct wl_shm_buffer *b=wl_shm_buffer_get(s->buffer);
        if(b) write_frame(b); else {puts("NON_SHM_BUFFER");fflush(stdout);}
        wl_resource_post_event(s->buffer,0);s->buffer=NULL;
    }
    for(unsigned i=0;i<s->count;i++) {wl_resource_post_event(s->callbacks[i],0,(uint32_t)now_ms());wl_resource_destroy(s->callbacks[i]);}
    s->count=0;
}
static const void *surface_impl[]={destroy,attach,rect,frame,region,region,commit,integer,integer,rect};
static void surface_free(struct wl_resource *r) {
    if(focus_surface==r) focus_surface=NULL;
    struct surface *s=wl_resource_get_user_data(r);
    for(unsigned i=0;i<s->count;i++) wl_resource_destroy(s->callbacks[i]);
    free(s);
}
static void create_surface(struct wl_client *c, struct wl_resource *r, uint32_t id) {
    struct wl_resource *s=wl_resource_create(c,&wl_surface_interface,wl_resource_get_version(r),id);
    wl_resource_set_implementation(s,surface_impl,calloc(1,sizeof(struct surface)),surface_free);
}
static const void *region_impl[]={destroy,rect,rect};
static void create_region(struct wl_client *c, struct wl_resource *r, uint32_t id) {
    (void)r;struct wl_resource *s=wl_resource_create(c,&wl_region_interface,1,id);
    wl_resource_set_implementation(s,region_impl,NULL,NULL);
}
static const void *compositor_impl[]={create_surface,create_region};
static void bind_compositor(struct wl_client *c,void *d,uint32_t v,uint32_t id) {
    (void)d;struct wl_resource *r=wl_resource_create(c,&wl_compositor_interface,v>4?4:v,id);
    wl_resource_set_implementation(r,compositor_impl,NULL,NULL);
}
static void configure(struct wl_client *c,struct wl_resource *r) {(void)c;wl_resource_post_event(r,1,0,1024,768);}
static void move(struct wl_client *c,struct wl_resource *r,struct wl_resource *s,uint32_t serial){(void)c;(void)r;(void)s;(void)serial;}
static void resize(struct wl_client *c,struct wl_resource *r,struct wl_resource *s,uint32_t serial,uint32_t edges){(void)edges;move(c,r,s,serial);}
static void transient(struct wl_client *c,struct wl_resource *r,struct wl_resource *p,int32_t x,int32_t y,uint32_t f){(void)p;(void)x;(void)y;(void)f;configure(c,r);}
static void fullscreen(struct wl_client *c,struct wl_resource *r,uint32_t method,uint32_t rate,struct wl_resource *o){(void)method;(void)rate;(void)o;configure(c,r);}
static void popup(struct wl_client *c,struct wl_resource *r,struct wl_resource *seat,uint32_t serial,struct wl_resource *parent,int32_t x,int32_t y,uint32_t flags){(void)seat;(void)serial;transient(c,r,parent,x,y,flags);}
static void maximized(struct wl_client *c,struct wl_resource *r,struct wl_resource *o){(void)o;configure(c,r);}
static void text_value(struct wl_client *c,struct wl_resource *r,const char *s){(void)c;(void)r;printf("SHELL_TEXT %s\n",s);fflush(stdout);}
static const void *shell_surface_impl[]={integer,move,resize,configure,transient,fullscreen,popup,maximized,text_value,text_value};
static void get_shell_surface(struct wl_client *c,struct wl_resource *r,uint32_t id,struct wl_resource *s){
    (void)r;struct wl_resource *t=wl_resource_create(c,&wl_shell_surface_interface,1,id);
    wl_resource_set_implementation(t,shell_surface_impl,s,NULL);
    if(!focus_surface) focus_surface=s;
}
static const void *shell_impl[]={get_shell_surface};
static void bind_shell(struct wl_client *c,void *d,uint32_t v,uint32_t id){
    (void)d;(void)v;struct wl_resource *r=wl_resource_create(c,&wl_shell_interface,1,id);
    wl_resource_set_implementation(r,shell_impl,NULL,NULL);
}
static void bind_output(struct wl_client *c,void *d,uint32_t v,uint32_t id){
    (void)d;if(v>2)v=2;struct wl_resource *r=wl_resource_create(c,&wl_output_interface,v,id);
    wl_resource_set_implementation(r,NULL,NULL,NULL);
    wl_resource_post_event(r,0,0,0,216,162,0,"QEMU","X2DII development",0);
    wl_resource_post_event(r,1,3,1024,768,60000);
    if(v>=2){wl_resource_post_event(r,3,1);wl_resource_post_event(r,2);}
}
static void position(struct wl_client *c,struct wl_resource *r,int32_t x,int32_t y){(void)c;(void)r;(void)x;(void)y;}
static const void *subsurface_impl[]={destroy,position,region,region,noop,noop};
static void get_subsurface(struct wl_client *c,struct wl_resource *r,uint32_t id,struct wl_resource *s,struct wl_resource *p){
    (void)r;(void)p;struct wl_resource *t=wl_resource_create(c,&wl_subsurface_interface,1,id);
    wl_resource_set_implementation(t,subsurface_impl,s,NULL);
}
static const void *subcompositor_impl[]={destroy,get_subsurface};
static void bind_subcompositor(struct wl_client *c,void *d,uint32_t v,uint32_t id){
    (void)d;(void)v;struct wl_resource *r=wl_resource_create(c,&wl_subcompositor_interface,1,id);
    wl_resource_set_implementation(r,subcompositor_impl,NULL,NULL);
}
static void touch_free(struct wl_resource *r){if(touch_resource==r)touch_resource=NULL;}
static void get_touch(struct wl_client *c,struct wl_resource *r,uint32_t id){
    (void)r;touch_resource=wl_resource_create(c,&wl_touch_interface,1,id);
    wl_resource_set_implementation(touch_resource,NULL,NULL,touch_free);
}
static const void *seat_impl[]={NULL,NULL,get_touch};
static void bind_seat(struct wl_client *c,void *d,uint32_t v,uint32_t id){
    (void)d;(void)v;struct wl_resource *r=wl_resource_create(c,&wl_seat_interface,1,id);
    wl_resource_set_implementation(r,seat_impl,NULL,NULL);
    wl_resource_post_event(r,0,4); /* touch only */
}
static void input_line(int fd,char *line){
    int x,y;char op[12];unsigned sequence=0;
    if(sscanf(line,"%11s %d %d %u",op,&x,&y,&sequence)==4){
        char ack[64];int size=snprintf(ack,sizeof(ack),"ACK %u\n",sequence);
        if(fd>=0)write(fd,ack,size);
    }
    if(sscanf(line,"%11s %d %d",op,&x,&y)==3 && x>=0 && x<1024 && y>=0 && y<768 && touch_resource && focus_surface){
      if(!strcmp(op,"tap") || (!strcmp(op,"down") && !touch_down)){
        wl_resource_post_event(touch_resource,0,wl_display_next_serial(server),(uint32_t)now_ms(),focus_surface,0,x*256,y*256);
        wl_resource_post_event(touch_resource,3);
        touch_down=1;
      }
      if(!strcmp(op,"move") && touch_down){
        wl_resource_post_event(touch_resource,2,(uint32_t)now_ms(),0,x*256,y*256);
        wl_resource_post_event(touch_resource,3);
      }
      if((!strcmp(op,"tap") || !strcmp(op,"up")) && touch_down){
        wl_resource_post_event(touch_resource,1,wl_display_next_serial(server),(uint32_t)now_ms(),0);
        wl_resource_post_event(touch_resource,3);
        touch_down=0;
      }
        if(strcmp(op,"move") && strcmp(op,"ping")){printf("TOUCH_%s %d %d\n",op,x,y);fflush(stdout);}
    }
}
struct input_stream {char bytes[4096];size_t used;int reply;};
static int input_ready(int fd,uint32_t mask,void *data){
    (void)mask;struct input_stream *s=data;
    ssize_t n=read(fd,s->bytes+s->used,sizeof(s->bytes)-1-s->used);
    if(n<=0)return 0;s->used+=n;s->bytes[s->used]=0;
    char *start=s->bytes,*end;
    while((end=strchr(start,'\n'))){*end=0;input_line(s->reply?fd:-1,start);start=end+1;}
    size_t remain=s->bytes+s->used-start;
    memmove(s->bytes,start,remain);s->used=remain;
    if(s->used==sizeof(s->bytes)-1)s->used=0;
    return 0;
}
int main(int argc,char **argv){
    if(argc<2 || argc>4){fprintf(stderr,"usage: mini_compositor GUEST_OUTPUT_DISK [VIRTIO_INPUT [VIRTIO_FRAMES]]\n");return 2;}
    output_path=argv[1];struct wl_display *d=wl_display_create();
    server=d;
    if(!d || wl_display_init_shm(d)<0 || wl_display_add_socket(d,"wayland-0")<0){perror("wayland init");return 1;}
    wl_global_create(d,&wl_compositor_interface,4,NULL,bind_compositor);
    wl_global_create(d,&wl_shell_interface,1,NULL,bind_shell);
    wl_global_create(d,&wl_output_interface,2,NULL,bind_output);
    wl_global_create(d,&wl_subcompositor_interface,1,NULL,bind_subcompositor);
    wl_global_create(d,&wl_seat_interface,1,NULL,bind_seat);
    const char *fifo="/dev/x2dii-input";
    unlink(fifo);if(mkfifo(fifo,0600)<0){perror("input FIFO");return 1;}
    int input_fd=open(fifo,O_RDWR|O_NONBLOCK|O_CLOEXEC);
    static struct input_stream fifo_stream,fast_stream;
    if(input_fd<0 || !wl_event_loop_add_fd(wl_display_get_event_loop(d),input_fd,1,input_ready,&fifo_stream)){perror("input event");return 1;}
    if(argc>=3){
        int fast_fd=open(argv[2],O_RDWR|O_NONBLOCK|O_CLOEXEC);fast_stream.reply=1;
        if(fast_fd<0 || !wl_event_loop_add_fd(wl_display_get_event_loop(d),fast_fd,1,input_ready,&fast_stream)){perror("virtio input");return 1;}
        puts("FAST_INPUT_READY");
    }
    if(argc==4){
        frame_fd=open(argv[3],O_WRONLY|O_CLOEXEC);
        if(frame_fd<0){perror("virtio frames");return 1;}
        puts("FAST_FRAMES_READY");
    }
    puts("MINI_COMPOSITOR_READY");fflush(stdout);wl_display_run(d);return 0;
}
