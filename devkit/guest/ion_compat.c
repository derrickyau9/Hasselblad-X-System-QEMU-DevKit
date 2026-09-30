/* QEMU-only replacement for legacy ION buffer allocation. No device ioctls.
 * Handles are owned file descriptors; buffers live in guest tmpfs and are
 * shared with the Wayland compositor through a client-owned (pid, fd) token.
 */
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#ifdef DEVKIT_TRACE
#include <stdio.h>
#include <signal.h>
#include <ucontext.h>
#include <dlfcn.h>
#define TRACE(...) fprintf(stderr,__VA_ARGS__)
static void crash(int sig, siginfo_t *info, void *context) {
    ucontext_t *u=context; Dl_info module={0};
    dladdr((void*)u->uc_mcontext.arm_pc,&module);
    fprintf(stderr,"UI_CRASH signal=%d addr=%p pc=%lx lr=%lx object=%s offset=%lx r0=%lx r1=%lx r2=%lx r3=%lx\n",sig,info->si_addr,
        u->uc_mcontext.arm_pc,u->uc_mcontext.arm_lr,module.dli_fname?module.dli_fname:"?",
        u->uc_mcontext.arm_pc-(unsigned long)module.dli_fbase,
        u->uc_mcontext.arm_r0,u->uc_mcontext.arm_r1,u->uc_mcontext.arm_r2,u->uc_mcontext.arm_r3);
    _exit(128+sig);
}
__attribute__((constructor)) static void tracing(void) {
    struct sigaction action={.sa_sigaction=crash,.sa_flags=SA_SIGINFO};
    sigemptyset(&action.sa_mask); sigaction(SIGSEGV,&action,NULL); sigaction(SIGBUS,&action,NULL);
}
#else
#define TRACE(...)
#endif

int ion_open(void) { int fd=open("/dev/null", O_RDWR | O_CLOEXEC); TRACE("ION_OPEN %d\n",fd); return fd; }
int ion_close(int fd) { return close(fd); }
int ion_alloc(int dev, size_t size, size_t align, unsigned heap, unsigned flags, int *handle) {
    (void)dev; (void)align; (void)heap; (void)flags;
    TRACE("ION_ALLOC dev=%d size=%u out=%p\n",dev,(unsigned)size,handle);
    if (!handle || !size || size > 128u*1024u*1024u) { errno=EINVAL; return -1; }
    char path[]="/dev/x2dii-runtime/buffer-XXXXXX";
    int fd=mkstemp(path);
    if(fd<0) return -1;
    unlink(path);
    if(ftruncate(fd,(off_t)size)<0) { close(fd); return -1; }
    *handle=fd; return 0;
}
int ion_free(int dev, int handle) { (void)dev; return close(handle); }
int ion_share(int dev, int handle, int *fd) {
    TRACE("ION_SHARE dev=%d handle=%d out=%p\n",dev,handle,fd);
    (void)dev; if(!fd) { errno=EINVAL; return -1; }
    *fd=dup(handle); return *fd<0 ? -1 : 0;
}
int ion_import(int dev, int fd, int *handle) { return ion_share(dev,fd,handle); }
int ion_map(int dev,int handle,size_t size,int prot,int flags,off_t offset,unsigned char **ptr,int *map_fd) {
    TRACE("ION_MAP dev=%d handle=%d size=%u ptr=%p fd=%p\n",dev,handle,(unsigned)size,ptr,map_fd);
    if(!ptr || ion_share(dev,handle,map_fd)<0) return -1;
    *ptr=mmap(NULL,size,prot,flags,*map_fd,offset);
    if(*ptr==MAP_FAILED) { close(*map_fd); *map_fd=-1; return -1; }
    return 0;
}
int ion_alloc_fd(int dev,size_t size,size_t align,unsigned heap,unsigned flags,int *fd) {
    return ion_alloc(dev,size,align,heap,flags,fd);
}
int ion_sync_fd(int dev,int fd) { (void)dev; (void)fd; return 0; }
int ion_custom_export_share_handle(int dev,int handle,uint64_t *shared) {
    (void)dev; if(!shared) return -1;
    *shared=((uint64_t)(unsigned)getpid()<<32)|(unsigned)handle; return 0;
}
int ion_custom_import_share_handle(int dev,uint64_t shared,int *handle) {
    return ion_import(dev,(int)shared,handle);
}
int ion_custom_get_phys_addr(int dev,int handle,unsigned *address,unsigned *size) {
    (void)dev; struct stat st;
    if(fstat(handle,&st)<0 || !address) return -1;
    *address=0; if(size) *size=(unsigned)st.st_size; return 0;
}
int ion_custom_sync(int dev,int handle,unsigned offset,unsigned size,unsigned direction) {
    (void)dev; (void)handle; (void)offset; (void)size; (void)direction; return 0;
}
