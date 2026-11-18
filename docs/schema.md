# YAML grammar

`yaml2qemu` reads a single YAML mapping and turns it into a QEMU command
line. Unknown keys are rejected so typos fail loudly. The MVP covers five
sections: machine, kernel, disks, networks, and console. Anything not
covered can be passed through with `extra_args`.

```yaml
arch: x86_64
machine:
  type: q35
  name: tiny-horse
  cpu: max
  smp: 2
  memory: 512M
  accel: auto
  nodefaults: true

kernel:
  image: bzImage
  initrd: initrd.img
  cmdline: root=/dev/vda rw console=ttyS0
  dtb: board.dtb

disks:
  - file: rootfs.ext4
    format: raw
    interface: virtio
    cache: writeback
  - file: seed.iso
    media: cdrom
    readonly: true

networks:
  - type: user
    model: virtio-net-pci
    hostfwd:
      - tcp:127.0.0.1:2222-:22
  - type: tap
    ifname: tap0
    script: false
    downscript: false

display: none
serial: mon:stdio
monitor: stdio

extra_args:
  - -no-reboot
```

## Top level

| Key          | Type              | Default                | QEMU output        | Description |
|--------------|-------------------|------------------------|--------------------|-------------|
| `binary`     | string            | selected from `arch`   | executable         | Override the QEMU binary. |
| `arch`       | string            | `x86_64`               | executable         | Selects the binary (see below). |
| `machine`    | string or mapping | *(omitted)*            | see below          | Machine/CPU/memory settings. |
| `kernel`     | string or mapping | *(omitted)*            | see below          | Kernel/initrd/cmdline. |
| `disks`      | list              | `[]`                   | `-drive`           | Disk devices. |
| `networks`   | list              | `[]`                   | `-netdev`/`-device`| Network devices. |
| `display`    | bool or string    | *(omitted)*            | `-display`         | `false` = `none`, `true` = default. |
| `serial`     | bool or string    | *(omitted)*            | `-serial`          | `true` = `mon:stdio`. |
| `monitor`    | bool or string    | *(omitted)*            | `-monitor`         | `true` = `stdio`. |
| `extra_args` | list or string    | `[]`                   | appended verbatim  | Escape hatch for anything else. |

### Architectures

`arch` selects the binary unless `binary` is set explicitly.

| `arch`                          | Binary |
|---------------------------------|--------|
| `x86_64`, `amd64`               | `qemu-system-x86_64` |
| `i386`, `i686`, `x86`           | `qemu-system-i386` |
| `aarch64`, `arm64`              | `qemu-system-aarch64` |
| `arm`                           | `qemu-system-arm` |
| `riscv64`                       | `qemu-system-riscv64` |
| `riscv32`                       | `qemu-system-riscv32` |
| `loongarch64`                   | `qemu-system-loongarch64` |
| `s390x`                         | `qemu-system-s390x` |

## `machine`

A string is shorthand for `{type: <string>}`.

| Key          | Type           | Default     | QEMU output   | Description |
|--------------|----------------|-------------|---------------|-------------|
| `type`       | string         | *(omitted)* | `-machine`    | Machine type, e.g. `q35`, `virt`. |
| `name`       | string         | *(omitted)* | `-name`       | Guest name. |
| `cpu`        | string         | *(omitted)* | `-cpu`        | CPU model. |
| `smp`        | int or string  | *(omitted)* | `-smp`        | Number of vCPUs. |
| `memory`     | int or string  | *(omitted)* | `-m`          | Guest memory, e.g. `512M`, `2G`. |
| `accel`      | string or list | *(omitted)* | `-accel`      | Accelerator(s). `auto` means `kvm` then `tcg`. |
| `kvm`        | bool           | *(omitted)* | `-accel`      | Shorthand: `true` = `kvm`, `false` = `tcg`. |
| `nodefaults` | bool           | `false`     | `-nodefaults` | Do not create default devices. |

`kvm` and `accel` are mutually exclusive.

## `kernel`

A string is shorthand for `{image: <string>}`.

| Key       | Type   | QEMU output | Description |
|-----------|--------|-------------|-------------|
| `image`   | string | `-kernel`   | Kernel image. |
| `initrd`  | string | `-initrd`   | Initial ramdisk. |
| `cmdline` | string | `-append`   | Kernel command line. |
| `dtb`     | string | `-dtb`      | Device tree blob. |

## `disks`

Each item is either a string (shorthand for `{file: <string>}`) or a
mapping. `file` is required.

| Key         | Type        | Default | QEMU output        | Description |
|-------------|-------------|---------|--------------------|-------------|
| `file`      | string      | —       | `file=`            | Disk image path. |
| `format`    | string      | `raw`   | `format=`          | Image format, e.g. `raw`, `qcow2`. |
| `interface` | string      | *(none)*| `if=`              | `virtio`, `ide`, `scsi`, `nvme`, ... |
| `media`     | string      | *(none)*| `media=`           | `disk` or `cdrom`. |
| `readonly`  | bool        | `false` | `readonly=on`      | Open read-only. |
| `id`        | string      | *(none)*| `id=`              | Drive identifier. |
| `boot`      | bool        | `false` | `boot=on`          | Make bootable. |
| `cache`     | string      | *(none)*| `cache=`           | e.g. `writeback`, `none`. |
| `discard`   | string      | *(none)*| `discard=`         | e.g. `unmap`. |
| `aio`       | string      | *(none)*| `aio=`             | e.g. `native`, `threads`. |
| `werror`    | string      | *(none)*| `werror=`          | Error policy. |
| `rerror`    | string      | *(none)*| `rerror=`          | Error policy. |
| `device`    | string      | *(none)*| `-device`          | Explicit block device frontend. |
| `extra`     | list        | `[]`    | appended to `-drive` | Raw `key=value` options. |

## `networks`

Each item is either a string (shorthand for `{type: <string>}`) or a
mapping. The default `type` is `user`.

Common keys:

| Key            | Type   | Default            | Description |
|----------------|--------|--------------------|-------------|
| `type`         | string | `user`             | `user`, `tap`, `bridge`, or `none`. |
| `id`           | string | `net<index>`       | Netdev identifier. |
| `model`        | string | `virtio-net-pci`   | NIC model; `none` omits `-device`. |
| `mac`          | string | *(none)*           | MAC address. |
| `device_extra` | list   | `[]`               | Extra `-device` options. |

### `type: user`

| Key          | Type        | Description |
|--------------|-------------|-------------|
| `hostfwd`    | list        | Port forwards, e.g. `tcp::2222-:22`. |
| `tftp`       | string      | TFTP root. |
| `bootfile`   | string      | DHCP boot file. |
| `dns`        | string      | DNS server. |
| `hostname`   | string      | DHCP hostname. |
| `domainname` | string      | DHCP domain name. |
| `restrict`   | bool        | Restrict guest network access. |
| `ipv6`       | bool        | Enable IPv6. |
| `extra`      | list        | Extra `-netdev` options. |

### `type: tap`

| Key          | Type        | Description |
|--------------|-------------|-------------|
| `ifname`     | string      | Host interface name. |
| `script`     | string/bool | Up script; `false` = `off`. |
| `downscript` | string/bool | Down script; `false` = `off`. |
| `br`         | string      | Bridge name. |
| `helper`     | string      | Bridge helper path. |
| `extra`      | list        | Extra `-netdev` options. |

### `type: bridge`

| Key      | Type   | Description |
|----------|--------|-------------|
| `br`     | string | Bridge name. |
| `helper` | string | Bridge helper path. |
| `extra`  | list   | Extra `-netdev` options. |

### `type: none`

Takes no other keys and emits `-nic none`.

## `extra_args`

A list of raw arguments, or a single shell-like string. Values are passed
to QEMU unchanged. Use this for options the grammar does not cover.

```yaml
extra_args: -no-reboot -snapshot
```
