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
int main(int argc,char **argv){
    setbuf(stdout,NULL);
    DBusConnection *c=dbus_bus_get(0,NULL);if(!c)return 1;
    const char *services[]={"camera","system","exmcu","settings","prodinfo","storage","error","upgrade","iio","phocus",
        "sysman","config","bodystate","camservice","pwrctrl","lens","seq","suc","ae","input","power","led","usbd","gpsd",
        "systemmanager","cambody","video","bodysync","farm","usbif","audio"};
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
                    /* HblmTypes uses bit masks: Xsystem=1024, Cfv907x=1048576. */
                    if(dest && !strcmp(dest,"com.hasselblad.seq")){
                        prop(&array,"camera_type",argc>1 && !strcmp(argv[1],"907x50c") ? 1048576 : 1024);
                        prop(&array,"camera_capabilities",2);
                    }
                    if(dest && !strcmp(dest,"com.hasselblad.cambody"))prop(&array,"capabilities",2);
                    if(dest && !strcmp(dest,"com.hasselblad.system")){
                        prop(&array,"system_state",1);prop(&array,"screen_status",0);
                        prop(&array,"language_index",0);prop(&array,"touch_screen_enabled",1);
                        prop(&array,"settings_mode",0);prop(&array,"tethered_mode",0);
                    }
                    if(dest && !strcmp(dest,"com.hasselblad.exmcu"))prop(&array,"battery_level",78);
                    if(dest && !strcmp(dest,"com.hasselblad.sysman")){
                        prop(&array,"system_state",1);prop(&array,"su_status",0);
                        prop(&array,"ui_power_state",0);prop(&array,"tethered_mode",0);
                    }
                    if(dest && !strcmp(dest,"com.hasselblad.bodystate")){
                        prop(&array,"system_state",1);prop(&array,"screens_active",1);
                        prop(&array,"screens_available",1);prop(&array,"current_backlight_power_mode",1);
                        prop(&array,"current_backlight_brightness",75);prop(&array,"proximity_detected",0);
                    }
                    if(dest && !strcmp(dest,"com.hasselblad.config")){
                        prop(&array,"GUI_idle_timeout",3600);prop(&array,"BACKLIGHT_brightness",75);
                        prop(&array,"BACKLIGHT_idle_brightness",75);
                        prop(&array,"gui_idle_timeout",3600);prop(&array,"sys_standby_idle_timeout",3600);
                        prop(&array,"sys_standby_idle_tethered_timeout",3600);
                        prop(&array,"custom_option_evf_preview_timeout",60);
                    }
                    if(dest && !strcmp(dest,"com.hasselblad.systemmanager"))prop(&array,"system_state",1);
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
