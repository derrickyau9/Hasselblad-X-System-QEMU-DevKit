/* Reproduce Android init's inherited socket contract in the disposable guest. */
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
int main(int argc,char **argv) {
    if(argc<2) return 2;
    const char *path="/dev/socket/dbus";
    int fd=socket(AF_UNIX,SOCK_STREAM,0);
    if(fd<0){perror("socket");return 1;}
    struct sockaddr_un address={.sun_family=AF_UNIX};
    strcpy(address.sun_path,path);
    unlink(path);
    if(bind(fd,(struct sockaddr*)&address,sizeof(address))<0){perror("bind");return 1;}
    chmod(path,0600);
    char value[32];snprintf(value,sizeof(value),"%d",fd);
    setenv("ANDROID_SOCKET_dbus",value,1);
    execv(argv[1],argv+1);perror("exec dbus");return 1;
}
