/* Development-only property providers on the private QEMU D-Bus. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef struct DBusConnection DBusConnection;
typedef struct DBusMessage DBusMessage;
/* libdbus documents the iterator as opaque, stack allocated ABI storage. */
typedef union {uint64_t align; unsigned char bytes[128];} Iter;
extern DBusConnection *dbus_bus_get(int,void *);
extern int dbus_bus_request_name(DBusConnection *,const char *,unsigned,void *);
extern int dbus_connection_read_write(DBusConnection *,int);
extern DBusMessage *dbus_connection_pop_message(DBusConnection *);
extern int dbus_message_get_type(DBusMessage *);
extern const char *dbus_message_get_member(DBusMessage *);
extern const char *dbus_message_get_interface(DBusMessage *);
extern const char *dbus_message_get_destination(DBusMessage *);
extern const char *dbus_message_get_path(DBusMessage *);
extern const char *dbus_message_get_signature(DBusMessage *);
extern DBusMessage *dbus_message_new_method_return(DBusMessage *);
extern DBusMessage *dbus_message_new_error(DBusMessage *,const char *,const char *);
extern void dbus_message_iter_init_append(DBusMessage *,Iter *);
extern int dbus_message_iter_open_container(Iter *,int,const char *,Iter *);
extern int dbus_message_iter_close_container(Iter *,Iter *);
extern int dbus_message_iter_append_basic(Iter *,int,const void *);
extern int dbus_connection_send(DBusConnection *,DBusMessage *,uint32_t *);
extern void dbus_connection_flush(DBusConnection *);
extern void dbus_message_unref(DBusMessage *);
static void prop(Iter *array,const char *name,int32_t value){
    Iter entry,variant;
    dbus_message_iter_open_container(array,'e',NULL,&entry);
    dbus_message_iter_append_basic(&entry,'s',&name);
    dbus_message_iter_open_container(&entry,'v',"i",&variant);
    dbus_message_iter_append_basic(&variant,'i',&value);
    dbus_message_iter_close_container(&entry,&variant);
    dbus_message_iter_close_container(array,&entry);
}
int main(void){
    setbuf(stdout,NULL);
    DBusConnection *c=dbus_bus_get(0,NULL);if(!c)return 1;
    const char *services[]={"camera","system","exmcu","settings","prodinfo","storage","error","upgrade","iio","phocus"};
    for(unsigned i=0;i<sizeof(services)/sizeof(*services);i++){
        char name[80];snprintf(name,sizeof(name),"com.hasselblad.%s",services[i]);
        if(dbus_bus_request_name(c,name,4,NULL)!=1){fprintf(stderr,"name unavailable: %s\n",name);return 1;}
    }
    puts("MOCK_SERVICES_READY");
    while(dbus_connection_read_write(c,100)){
        DBusMessage *m;
        while((m=dbus_connection_pop_message(c))){
            if(dbus_message_get_type(m)==1){
                const char *member=dbus_message_get_member(m), *dest=dbus_message_get_destination(m);
                printf("MOCK_CALL %s %s %s %s\n",dest?dest:"",dbus_message_get_path(m),member?member:"",dbus_message_get_signature(m));
                DBusMessage *reply;
                if(member && !strcmp(member,"GetAll")){
                    reply=dbus_message_new_method_return(m);Iter root,array;
                    dbus_message_iter_init_append(reply,&root);
                    dbus_message_iter_open_container(&root,'a',"{sv}",&array);
                    /* Only synthetic UI state; no capture or device control. */
                    if(dest && !strcmp(dest,"com.hasselblad.camera"))prop(&array,"live_view_state",0);
                    if(dest && !strcmp(dest,"com.hasselblad.system")){
                        prop(&array,"system_state",1);prop(&array,"screen_status",0);
                        prop(&array,"language_index",0);prop(&array,"touch_screen_enabled",1);
                        prop(&array,"settings_mode",0);prop(&array,"tethered_mode",0);
                    }
                    if(dest && !strcmp(dest,"com.hasselblad.exmcu"))prop(&array,"battery_level",78);
                    dbus_message_iter_close_container(&root,&array);
                }else reply=dbus_message_new_error(m,"org.freedesktop.DBus.Error.NotSupported","UI development mock: method is not implemented");
                dbus_connection_send(c,reply,NULL);dbus_message_unref(reply);
            }
            dbus_message_unref(m);
        }
        dbus_connection_flush(c);
    }
    return 0;
}
