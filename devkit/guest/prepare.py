"""Generate isolated writable disks; SDK originals remain untouched."""
from pathlib import Path
import shutil
import tempfile
from pyfdt.pyfdt import FdtBlobParse, FdtNode, FdtPropertyStrings
from .gpt import patched_chunks
from ..core import Task, write_json, read_json
from ..models import MODELS, model_id

def _qemu(qemu, name):
    path = qemu / name
    if path.exists():
        return path
    windows = qemu / (name + '.exe')
    if windows.exists():
        return windows
    return path

def prepare(device, runtime, task=None):
    task = task or Task()
    image, qemu = Path(runtime['image']), Path(runtime['qemu'])
    if ',' in str(device):
        raise ValueError('Choose a data directory without commas')
    task.report('Preparing disposable guest / 准备独立虚拟机…')
    recorded = read_json(device / 'guest-runtime.json')
    if recorded and recorded != runtime:
        raise ValueError('Runtime location changed. Restore the previous runtime path or import into a new DevKit data directory.')
    if not (device / 'android-virt.dtb').exists():
        base = device / 'virt.dtb'
        task.run([_qemu(qemu, 'qemu-system-aarch64'), '-machine', f'virt,dumpdtb={base}', '-cpu', 'cortex-a57', '-display', 'none'])
        with base.open('rb') as stream:
            tree = FdtBlobParse(stream).to_fdt()
        firmware, android, fstab, vendor = [FdtNode(n) for n in ('firmware', 'android', 'fstab', 'vendor')]
        def prop(node, name, value):
            node.append(FdtPropertyStrings(name, [value]))
        prop(android, 'compatible', 'android,firmware')
        prop(fstab, 'compatible', 'android,fstab')
        for name, value in {'compatible': 'android,vendor', 'dev': '/dev/block/vdb1', 'type': 'ext4', 'mnt_flags': 'ro', 'fsmgr_flags': 'wait'}.items():
            prop(vendor, name, value)
        fstab.append(vendor); android.append(fstab); firmware.append(android)
        tree.get_rootnode().append(firmware)
        (device / 'android-virt.dtb').write_bytes(tree.to_dtb())
    for kind, label in [('system', 'vda1'), ('vendor', 'vdb1')]:
        output = device / f'{kind}-name.qcow2'
        if output.exists():
            continue
        temporary = device / f'{kind}-name.partial.qcow2'
        task.run([_qemu(qemu, 'qemu-img'), 'create', '-q', '-f', 'qcow2', '-F', 'raw', '-b', image / f'{kind}.img', temporary])
        with tempfile.TemporaryDirectory(prefix='gpt-', dir=device) as temp:
            args = [_qemu(qemu, 'qemu-io'), '-f', 'qcow2']
            for n, (offset, chunk) in enumerate(patched_chunks(image / f'{kind}.img', label)):
                path = Path(temp) / f'patch-{n}.bin'
                path.write_bytes(chunk)
                args += ['-c', f'write -q -s {path.name} {offset} {len(chunk)}']
            task.run([*args, temporary], cwd=temp)
        temporary.replace(output)
    data = device / 'userdata-qemu.img'
    if not data.exists():
        temporary = device / 'userdata.partial.img'
        task.run([runtime['mke2fs'], '-q', '-F', '-t', 'ext4', '-b', '4096', temporary, '524288'], timeout=300)
        temporary.replace(data)
    key = device / 'encryptionkey-qemu.img'
    if not key.exists():
        shutil.copy2(image / 'encryptionkey.img', key)
    write_json(device / 'guest-runtime.json', runtime)
    if read_json(device / 'device.json').get('abi') == 'linux-arm32' and not (device / 'linux-root.img').exists():
        temporary = device / 'linux-root.partial.img'
        task.run([runtime['mke2fs'], '-q', '-F', '-t', 'ext4', '-b', '4096', temporary, '524288'], timeout=300)
        temporary.replace(device / 'linux-root.img')

def command(device, runtime, console_port, input_port, frame_port):
    image, qemu = Path(runtime['image']), Path(runtime['qemu'])
    profile = read_json(device / 'device.json') or {}
    hw_version = MODELS[model_id(profile)]['hardware']
    args = [str(_qemu(qemu, 'qemu-system-aarch64')), '-machine', 'virt', '-cpu', 'cortex-a57',
            '-m', '2048', '-smp', '2', '-accel', 'tcg,thread=multi,tb-size=512', '-display', 'none',
            '-monitor', 'none', '-no-reboot', '-nic', 'none',
            '-serial', f'tcp:127.0.0.1:{console_port},server=on,wait=off',
            '-kernel', str(image / 'kernel-ranchu'), '-dtb', str(device / 'android-virt.dtb'),
            '-append', 'console=ttyAMA0 earlycon=pl011,0x09000000 loglevel=1 quiet androidboot.hardware=ranchu '
                       f'hw_version={hw_version} mp_state=production lcd_type=0 root=/dev/vda1 rootwait ro rootfstype=ext4 init=/init skip_initramfs']
    # virtio-mmio disks enumerate in reverse attachment order with this SDK kernel.
    if profile.get('abi') == 'linux-arm32':
        args += ['-drive', f'if=none,id=linuxroot,file={device / "linux-root.img"},format=raw',
                 '-device', 'virtio-blk-device,drive=linuxroot']
    for name, file, options in [
        ('framebuffer', str(device / 'framebuffer.raw'), 'format=raw,cache=unsafe'),
        ('payload', 'fat:ro:' + str(device / 'payload-stage'), 'format=raw,readonly=on'),
        ('encryption', str(device / 'encryptionkey-qemu.img'), 'format=raw'),
        ('data', str(device / 'userdata-qemu.img'), 'format=raw'),
        ('vendor', str(device / 'vendor-name.qcow2'), 'format=qcow2,readonly=on'),
        ('system', str(device / 'system-name.qcow2'), 'format=qcow2,snapshot=on')]:
        args += ['-drive', f'if=none,id={name},file={file},{options}', '-device', f'virtio-blk-device,drive={name}']
    args += ['-device', 'virtio-rng-device', '-device', 'virtio-serial-device']
    for identifier, port, name in [('uiinput', input_port, 'x2dii.input'), ('uiframes', frame_port, 'x2dii.frames')]:
        args += ['-chardev', f'socket,id={identifier},host=127.0.0.1,port={port},server=on,wait=off',
                 '-device', f'virtserialport,chardev={identifier},name={name}']
    return args
