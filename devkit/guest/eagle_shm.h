/* Legacy camera Qt uses eagle_shm instead of wl_shm. The guest ION shim
 * supplies a (pid, fd) token for an ordinary shared buffer. Only buffers
 * owned by this Wayland client are accepted; no hardware memory is mapped.
 */
struct wl_message {const char *name,*signature;const struct wl_interface **types;};
struct wl_interface {const char *name;int version,method_count;const struct wl_message *methods;int event_count;const struct wl_message *events;};
extern const struct wl_interface wl_buffer_interface;
extern int wl_resource_instance_of(struct wl_resource *,const struct wl_interface *,const void *);
extern void wl_client_get_credentials(struct wl_client *,pid_t *,uid_t *,gid_t *);
extern void wl_resource_post_error(struct wl_resource *,uint32_t,const char *,...);
static const struct wl_interface eagle_pool_interface;
static const struct wl_interface *eagle_pool_types[]={&eagle_pool_interface};
static const struct wl_interface *eagle_buffer_types[]={&wl_buffer_interface,NULL,NULL,NULL,NULL,NULL,NULL};
static const struct wl_message eagle_requests[]={{"create_pool","n",eagle_pool_types}};
static const struct wl_message eagle_events[]={{"format","u",NULL}};
static const struct wl_interface eagle_shm_interface={"eagle_shm",1,1,eagle_requests,1,eagle_events};
static const struct wl_message eagle_pool_requests[]={
    {"create_buffer","nuuiiiu",eagle_buffer_types},{"destroy","",NULL}};
static const struct wl_interface eagle_pool_interface={"eagle_shm_pool",1,2,eagle_pool_requests,0,NULL};
struct eagle_buffer {void *pixels;size_t size;int width,height,stride;};
static const void *eagle_buffer_impl[]={destroy};
static void free_eagle_buffer(struct wl_resource *r) {
    struct eagle_buffer *b=wl_resource_get_user_data(r);
    if(b){munmap(b->pixels,b->size);free(b);}
}
static int write_eagle_buffer(struct surface *s,struct wl_resource *r) {
    if(!wl_resource_instance_of(r,&wl_buffer_interface,eagle_buffer_impl))return 0;
    struct eagle_buffer *b=wl_resource_get_user_data(r);
    capture_pixels(s,b->width,b->height,b->stride,1,b->pixels);return 1;
}
static void create_eagle_buffer(struct wl_client *c,struct wl_resource *r,uint32_t id,
        uint32_t low,uint32_t high,int32_t width,int32_t height,int32_t stride,uint32_t format) {
    pid_t pid;uid_t uid;gid_t gid;wl_client_get_credentials(c,&pid,&uid,&gid);
    if(high!=(uint32_t)pid || low>1048576 || width<=0 || height<=0 || width>4096 || height>4096 || stride<width || stride>32768) {
        wl_resource_post_error(r,0,"invalid development buffer");return;
    }
    char path[80];snprintf(path,sizeof(path),"/proc/%u/fd/%u",high,low);
    int fd=open(path,O_RDONLY|O_CLOEXEC);struct stat st;
    if(fd<0 || fstat(fd,&st)<0 || !S_ISREG(st.st_mode)) {
        if(fd>=0)close(fd);wl_resource_post_error(r,0,"shared buffer unavailable");return;
    }
    /* Earlier Eagle clients report bytes; newer ones report pixels. */
    size_t line=(size_t)stride*4;
    if(st.st_size<(off_t)(line*height) && stride>=width*4)line=(size_t)stride;
    size_t size=line*height;
    if(line>32768 || size>32*1024*1024 || st.st_size<(off_t)size){
        fprintf(stderr,"EAGLE_SIZE width=%d height=%d stride=%d capacity=%lld\n",width,height,stride,(long long)st.st_size);
        close(fd);wl_resource_post_error(r,0,"shared buffer too small");return;
    }
    void *pixels=mmap(NULL,size,PROT_READ,MAP_SHARED,fd,0);close(fd);
    if(pixels==MAP_FAILED){wl_resource_post_error(r,0,"buffer mapping failed");return;}
    struct eagle_buffer *b=calloc(1,sizeof(*b));
    if(!b){munmap(pixels,size);wl_resource_post_error(r,0,"buffer allocation failed");return;}
    *b=(struct eagle_buffer){pixels,size,width,height,(int)line};
    struct wl_resource *buffer=wl_resource_create(c,&wl_buffer_interface,1,id);
    wl_resource_set_implementation(buffer,eagle_buffer_impl,b,free_eagle_buffer);
    printf("EAGLE_BUFFER %dx%d stride=%d format=%u\n",width,height,stride,format);fflush(stdout);
}
static const void *eagle_pool_impl[]={create_eagle_buffer,destroy};
static void create_eagle_pool(struct wl_client *c,struct wl_resource *r,uint32_t id) {
    (void)r;struct wl_resource *pool=wl_resource_create(c,&eagle_pool_interface,1,id);
    wl_resource_set_implementation(pool,eagle_pool_impl,NULL,NULL);
}
static const void *eagle_shm_impl[]={create_eagle_pool};
static void bind_eagle_shm(struct wl_client *c,void *d,uint32_t v,uint32_t id) {
    (void)d;(void)v;struct wl_resource *r=wl_resource_create(c,&eagle_shm_interface,1,id);
    wl_resource_set_implementation(r,eagle_shm_impl,NULL,NULL);
    wl_resource_post_event(r,0,0);wl_resource_post_event(r,0,1);
}
