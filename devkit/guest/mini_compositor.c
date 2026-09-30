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
#include <sys/mman.h>

struct wl_display; struct wl_client; struct wl_resource; struct wl_interface;
struct wl_shm_buffer; struct wl_global;
extern const struct wl_interface wl_compositor_interface, wl_surface_interface;
extern const struct wl_interface wl_region_interface, wl_shell_interface;
extern const struct wl_interface wl_shell_surface_interface, wl_callback_interface;
extern const struct wl_interface wl_output_interface, wl_subcompositor_interface;
extern const struct wl_interface wl_subsurface_interface;
extern const struct wl_interface wl_seat_interface, wl_touch_interface;
extern const struct wl_interface wl_keyboard_interface;
struct wl_event_loop; struct wl_event_source;
struct wl_list {struct wl_list *prev,*next;};
struct wl_listener {struct wl_list link;void (*notify)(struct wl_listener *,void *);};
extern void wl_resource_add_destroy_listener(struct wl_resource *,struct wl_listener *);
extern struct wl_event_loop *wl_display_get_event_loop(struct wl_display *);
extern struct wl_event_source *wl_event_loop_add_fd(struct wl_event_loop *, int, uint32_t,
    int (*)(int,uint32_t,void *),void *);
extern struct wl_event_source *wl_event_loop_add_timer(struct wl_event_loop *,int (*)(void *),void *);
extern int wl_event_source_timer_update(struct wl_event_source *,int);
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
extern struct wl_client *wl_resource_get_client(struct wl_resource *);
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

struct damage_rect {int32_t x,y,w,h;};
struct surface {
    struct wl_resource *resource;
    struct wl_resource *buffer;
    struct wl_resource *callbacks[32];
    unsigned count;
    struct wl_resource *ready_callbacks[32];
    unsigned ready_count;
    struct surface *next;
    unsigned char *pixels;
    int width,height;
    struct damage_rect damage[1024];
    unsigned damage_count;
    int full_damage;
};
static const char *output_path;
static unsigned frame_number;
static uint64_t total_frame_ms;
static int frame_fd=-1;
static struct wl_display *server;
static struct surface *surfaces;
static struct wl_event_source *frame_timer;
static int frame_timer_pending;
struct pending_release {
    struct wl_listener listener;struct wl_resource *buffer;struct pending_release *next;
    struct surface *surface;struct damage_rect damage[1024];unsigned damage_count;int full_damage;
};
static struct pending_release *pending_releases;
static void capture_buffer(struct surface *,struct wl_resource *,const struct damage_rect *,unsigned,int);
static struct wl_resource *touch_resource, *focus_surface;
static struct wl_resource *keyboard_resource;
static struct wl_resource *keyboard_focus;
static struct wl_resource *output_resource;
static int touch_down;
static int output_width=1024,output_height=768;
static uint64_t now_ms(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}
static void destroy(struct wl_client *c, struct wl_resource *r) {(void)c; wl_resource_destroy(r);}
static void rect(struct wl_client *c, struct wl_resource *r, int32_t x, int32_t y, int32_t w, int32_t h) {
    (void)c; (void)r; (void)x; (void)y; (void)w; (void)h;
}
static void damage(struct wl_client *c,struct wl_resource *r,int32_t x,int32_t y,int32_t w,int32_t h){
    (void)c;struct surface *s=wl_resource_get_user_data(r);
    if(w<=0 || h<=0)return;
    if(s->damage_count>=1024){s->full_damage=1;return;}
    unsigned i=s->damage_count++;s->damage[i].x=x;s->damage[i].y=y;s->damage[i].w=w;s->damage[i].h=h;
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
static int finish_frames(void *data){
    (void)data;frame_timer_pending=0;
    /* Present commits in order, while their buffers still belong to the server. */
    struct pending_release *ordered=NULL;
    while(pending_releases){
        struct pending_release *item=pending_releases;pending_releases=item->next;
        item->next=ordered;ordered=item;
    }
    pending_releases=ordered;
    while(pending_releases){
        struct pending_release *item=pending_releases;pending_releases=item->next;
        if(item->surface)capture_buffer(item->surface,item->buffer,item->damage,item->damage_count,item->full_damage);
        item->listener.link.prev->next=item->listener.link.next;
        item->listener.link.next->prev=item->listener.link.prev;
        wl_resource_post_event(item->buffer,0);free(item);
    }
    for(struct surface *s=surfaces;s;s=s->next){
        for(unsigned i=0;i<s->ready_count;i++){
            wl_resource_post_event(s->ready_callbacks[i],0,(uint32_t)now_ms());
            wl_resource_destroy(s->ready_callbacks[i]);
        }
        s->ready_count=0;
    }
    return 0;
}
static void released_buffer_destroyed(struct wl_listener *listener,void *data){
    (void)data;struct pending_release *item=(struct pending_release *)listener;
    struct pending_release **entry=&pending_releases;
    while(*entry && *entry!=item)entry=&(*entry)->next;
    if(*entry)*entry=item->next;
    listener->link.prev->next=listener->link.next;
    listener->link.next->prev=listener->link.prev;
    free(item);
}
static void defer_release(struct wl_resource *buffer,struct surface *s){
    for(struct pending_release *p=pending_releases;p;p=p->next)if(p->buffer==buffer){
        p->full_damage|=s->full_damage;
        if(p->damage_count+s->damage_count>1024)p->full_damage=1;
        else {memcpy(p->damage+p->damage_count,s->damage,s->damage_count*sizeof(*s->damage));p->damage_count+=s->damage_count;}
        return;
    }
    struct pending_release *item=calloc(1,sizeof(*item));
    if(!item){wl_resource_post_event(buffer,0);return;}
    item->buffer=buffer;item->next=pending_releases;pending_releases=item;
    item->surface=s;item->damage_count=s->damage_count;item->full_damage=s->full_damage;
    memcpy(item->damage,s->damage,s->damage_count*sizeof(*s->damage));
    item->listener.notify=released_buffer_destroyed;
    wl_resource_add_destroy_listener(buffer,&item->listener);
}
static void write_pixels(int w,int h,int stride,uint32_t format,const void *pixels) {
    uint64_t began=now_ms();
    if (w<=0 || h<=0 || w>4096 || h>4096 || stride<w*4 || stride>32768 || format>1) return;
    if(frame_fd>=0){
        uint32_t head[128]={0x58463244,w,h,stride,format,++frame_number};
        int failed=write_all(frame_fd,head,sizeof(head));
        if(!failed)failed=write_all(frame_fd,pixels,(size_t)stride*h);
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
    uint32_t invalid=0;
    if(pwrite(fd,&invalid,sizeof(invalid),0)==sizeof(invalid)) {
        size_t offset=0;
        while(offset<bytes) {ssize_t n=pwrite(fd,(const char*)pixels+offset,bytes-offset,sizeof(header)+offset);if(n<=0)break;offset+=n;}
        if(offset==bytes)pwrite(fd,header,sizeof(header),0);
        fsync(fd);
        total_frame_ms+=now_ms()-began;
        if(frame_number==1 || frame_number%30==0){
            printf("CAMERA_FRAME %u %dx%d bytes=%zu average_write_ms=%llu\n",frame_number,w,h,offset,(unsigned long long)(total_frame_ms/frame_number));fflush(stdout);
        }
    }
    close(fd);
}
static void capture_pixels(struct surface *s,int width,int height,int stride,uint32_t format,const void *pixels){
    if(width<=0 || height<=0 || width>4096 || height>4096 || stride<width*4 || stride>32768 || (size_t)width*height*4>32*1024*1024)return;
    if(getenv("DEVKIT_TRACE_DAMAGE")){
        unsigned colored=0,opaque=0;
        for(int y=0;y<height;y+=8)for(int x=0;x<width;x+=8){uint32_t p=*(const uint32_t*)((const char*)pixels+(size_t)y*stride+x*4);colored+=(p&0xffffff)!=0;opaque+=(p>>24)!=0;}
        printf("DAMAGE_FRAME %u color=%u alpha=%u rects=%u full=%d",frame_number+1,colored,opaque,s->damage_count,s->full_damage);
        for(unsigned i=0;i<s->damage_count && i<12;i++)printf(" [%d,%d,%d,%d]",s->damage[i].x,s->damage[i].y,s->damage[i].w,s->damage[i].h);
        puts("");fflush(stdout);
    }
    if(!s->pixels || s->width!=width || s->height!=height){
        free(s->pixels);s->pixels=calloc((size_t)width*height,4);s->width=width;s->height=height;s->full_damage=1;
        if(!s->pixels)return;
    }
    if(s->full_damage){
        for(int y=0;y<height;y++)memcpy(s->pixels+(size_t)y*width*4,(const char*)pixels+(size_t)y*stride,(size_t)width*4);
    }else for(unsigned i=0;i<s->damage_count;i++){
        int64_t x=s->damage[i].x,y=s->damage[i].y,x2=x+s->damage[i].w,y2=y+s->damage[i].h;
        if(x<0)x=0;if(y<0)y=0;if(x2>width)x2=width;if(y2>height)y2=height;
        if(x>=x2 || y>=y2)continue;
        for(;y<y2;y++)memcpy(s->pixels+((size_t)y*width+x)*4,(const char*)pixels+(size_t)y*stride+x*4,(size_t)(x2-x)*4);
    }
    if(s->resource==focus_surface)write_pixels(width,height,width*4,format,s->pixels);
}
#include "eagle_shm.h"
static void capture_buffer(struct surface *s,struct wl_resource *buffer,const struct damage_rect *rects,unsigned count,int full){
    s->damage_count=count;s->full_damage=full;memcpy(s->damage,rects,count*sizeof(*rects));
    struct wl_shm_buffer *b=wl_shm_buffer_get(buffer);
    if(b){
        wl_shm_buffer_begin_access(b);
        capture_pixels(s,wl_shm_buffer_get_width(b),wl_shm_buffer_get_height(b),wl_shm_buffer_get_stride(b),wl_shm_buffer_get_format(b),wl_shm_buffer_get_data(b));
        wl_shm_buffer_end_access(b);
    }else if(!write_eagle_buffer(s,buffer)){puts("NON_SHM_BUFFER");fflush(stdout);}
    s->damage_count=0;s->full_damage=0;
}
static void commit(struct wl_client *c, struct wl_resource *r) {
    (void)c;struct surface *s=wl_resource_get_user_data(r);
    if(s->buffer) {
        defer_release(s->buffer,s);s->buffer=NULL;
    }
    for(unsigned i=0;i<s->count;i++){
        if(s->ready_count<32)s->ready_callbacks[s->ready_count++]=s->callbacks[i];
        else wl_resource_destroy(s->callbacks[i]);
    }
    /* Signal a display tick after the commit, rather than recursively driving
     * Qt's software renderer with callbacks in the same dispatch cycle. */
    if((s->ready_count || pending_releases) && !frame_timer_pending){
        frame_timer_pending=1;wl_event_source_timer_update(frame_timer,16);
    }
    s->count=0;
    s->damage_count=0;s->full_damage=0;
}
static const void *surface_impl[]={destroy,attach,damage,frame,region,region,commit,integer,integer,damage};
static void surface_free(struct wl_resource *r) {
    if(focus_surface==r) focus_surface=NULL;
    if(keyboard_focus==r) keyboard_focus=NULL;
    struct surface *s=wl_resource_get_user_data(r);
    for(struct pending_release *p=pending_releases;p;p=p->next)if(p->surface==s)p->surface=NULL;
    for(unsigned i=0;i<s->count;i++) wl_resource_destroy(s->callbacks[i]);
    for(unsigned i=0;i<s->ready_count;i++) wl_resource_destroy(s->ready_callbacks[i]);
    struct surface **item=&surfaces;
    while(*item && *item!=s)item=&(*item)->next;
    if(*item)*item=s->next;
    free(s->pixels);free(s);
}
static void create_surface(struct wl_client *c, struct wl_resource *r, uint32_t id) {
    struct wl_resource *s=wl_resource_create(c,&wl_surface_interface,wl_resource_get_version(r),id);
    struct surface *state=calloc(1,sizeof(struct surface));
    state->resource=s;
    state->next=surfaces;surfaces=state;
    wl_resource_set_implementation(s,surface_impl,state,surface_free);
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
static void configure(struct wl_client *c,struct wl_resource *r) {(void)c;wl_resource_post_event(r,1,0,output_width,output_height);}
static void move(struct wl_client *c,struct wl_resource *r,struct wl_resource *s,uint32_t serial){(void)c;(void)r;(void)s;(void)serial;}
static void resize(struct wl_client *c,struct wl_resource *r,struct wl_resource *s,uint32_t serial,uint32_t edges){(void)edges;move(c,r,s,serial);}
static void transient(struct wl_client *c,struct wl_resource *r,struct wl_resource *p,int32_t x,int32_t y,uint32_t f){(void)p;(void)x;(void)y;(void)f;configure(c,r);}
static void fullscreen(struct wl_client *c,struct wl_resource *r,uint32_t method,uint32_t rate,struct wl_resource *o){(void)method;(void)rate;(void)o;configure(c,r);}
static void popup(struct wl_client *c,struct wl_resource *r,struct wl_resource *seat,uint32_t serial,struct wl_resource *parent,int32_t x,int32_t y,uint32_t flags){(void)seat;(void)serial;transient(c,r,parent,x,y,flags);}
static void maximized(struct wl_client *c,struct wl_resource *r,struct wl_resource *o){(void)o;configure(c,r);}
static void text_value(struct wl_client *c,struct wl_resource *r,const char *s){(void)c;if(!strcmp(s,"main"))focus_surface=wl_resource_get_user_data(r);printf("SHELL_TEXT %s\n",s);fflush(stdout);}
static const void *shell_surface_impl[]={integer,move,resize,configure,transient,fullscreen,popup,maximized,text_value,text_value};
static void get_shell_surface(struct wl_client *c,struct wl_resource *r,uint32_t id,struct wl_resource *s){
    (void)r;struct wl_resource *t=wl_resource_create(c,&wl_shell_surface_interface,1,id);
    wl_resource_set_implementation(t,shell_surface_impl,s,NULL);
    if(!focus_surface) focus_surface=s;
    if(output_resource && wl_resource_get_client(output_resource)==c)wl_resource_post_event(s,0,output_resource);
}
static const void *shell_impl[]={get_shell_surface};
static void bind_shell(struct wl_client *c,void *d,uint32_t v,uint32_t id){
    (void)d;(void)v;struct wl_resource *r=wl_resource_create(c,&wl_shell_interface,1,id);
    wl_resource_set_implementation(r,shell_impl,NULL,NULL);
}
static void output_free(struct wl_resource *r){if(output_resource==r)output_resource=NULL;}
static void bind_output(struct wl_client *c,void *d,uint32_t v,uint32_t id){
    (void)d;if(v>2)v=2;struct wl_resource *r=wl_resource_create(c,&wl_output_interface,v,id);
    output_resource=r;wl_resource_set_implementation(r,NULL,NULL,output_free);
    wl_resource_post_event(r,0,0,0,216,162,0,"QEMU","X2DII development",0);
    wl_resource_post_event(r,1,3,output_width,output_height,60000);
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
static void keyboard_free(struct wl_resource *r){if(keyboard_resource==r){keyboard_resource=NULL;keyboard_focus=NULL;}}
static void get_keyboard(struct wl_client *c,struct wl_resource *r,uint32_t id){
    (void)r;
    static const char map[]="xkb_keymap { xkb_keycodes \"devkit\" { minimum=8; maximum=255; <ESC>=9; <FK01>=67; <FK02>=68; <FK03>=69; <FK04>=70; <FK05>=71; }; xkb_types \"devkit\" { type \"ONE_LEVEL\" { modifiers=None; map[None]=Level1; level_name[Level1]=\"Any\"; }; }; xkb_compatibility \"devkit\" {}; xkb_symbols \"devkit\" { key <ESC> { [ Escape ] }; key <FK01> { [ F1 ] }; key <FK02> { [ F2 ] }; key <FK03> { [ F3 ] }; key <FK04> { [ F4 ] }; key <FK05> { [ F5 ] }; }; };";
    char name[]="/dev/x2dii-runtime/keymap-XXXXXX";int fd=mkstemp(name);
    if(fd<0)return;unlink(name);
    if(write_all(fd,map,sizeof(map))<0){close(fd);return;}
    keyboard_resource=wl_resource_create(c,&wl_keyboard_interface,1,id);
    wl_resource_set_implementation(keyboard_resource,NULL,NULL,keyboard_free);
    wl_resource_post_event(keyboard_resource,0,1,fd,(uint32_t)sizeof(map));close(fd);
}
static const void *seat_impl[]={NULL,get_keyboard,get_touch};
static void bind_seat(struct wl_client *c,void *d,uint32_t v,uint32_t id){
    (void)d;(void)v;struct wl_resource *r=wl_resource_create(c,&wl_seat_interface,1,id);
    wl_resource_set_implementation(r,seat_impl,NULL,NULL);
    wl_resource_post_event(r,0,6); /* keyboard and touch */
}
static void input_line(int fd,char *line){
    int x,y;char op[12];unsigned sequence=0;
    if(sscanf(line,"key %d %d",&x,&y)==2 && keyboard_resource && focus_surface && (x==1 || (x>=59 && x<=63)) && (y==0 || y==1)){
        struct {size_t size,alloc;void *data;} keys={0,0,NULL};
        if(keyboard_focus!=focus_surface){
            if(keyboard_focus)wl_resource_post_event(keyboard_resource,2,wl_display_next_serial(server),keyboard_focus);
            wl_resource_post_event(keyboard_resource,1,wl_display_next_serial(server),focus_surface,&keys);
            keyboard_focus=focus_surface;
        }
        wl_resource_post_event(keyboard_resource,3,wl_display_next_serial(server),(uint32_t)now_ms(),(uint32_t)x,(uint32_t)y);
        return;
    }
    if(sscanf(line,"%11s %d %d %u",op,&x,&y,&sequence)==4){
        char ack[64];int size=snprintf(ack,sizeof(ack),"ACK %u\n",sequence);
        if(fd>=0)write(fd,ack,size);
    }
    if(sscanf(line,"%11s %d %d",op,&x,&y)==3 && x>=0 && x<output_width && y>=0 && y<output_height && touch_resource && focus_surface){
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
    if(getenv("DEVKIT_LEGACY_DISPLAY")){output_width=640;output_height=480;}
    if(argc<2 || argc>4){fprintf(stderr,"usage: mini_compositor GUEST_OUTPUT_DISK [VIRTIO_INPUT [VIRTIO_FRAMES]]\n");return 2;}
    output_path=argv[1];struct wl_display *d=wl_display_create();
    server=d;
    if(!d || wl_display_init_shm(d)<0 || wl_display_add_socket(d,"wayland-0")<0){perror("wayland init");return 1;}
    frame_timer=wl_event_loop_add_timer(wl_display_get_event_loop(d),finish_frames,NULL);
    if(!frame_timer){perror("frame timer");return 1;}
    wl_global_create(d,&wl_compositor_interface,4,NULL,bind_compositor);
    wl_global_create(d,&wl_shell_interface,1,NULL,bind_shell);
    wl_global_create(d,&wl_output_interface,2,NULL,bind_output);
    wl_global_create(d,&wl_subcompositor_interface,1,NULL,bind_subcompositor);
    wl_global_create(d,&wl_seat_interface,1,NULL,bind_seat);
    wl_global_create(d,&eagle_shm_interface,1,NULL,bind_eagle_shm);
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
