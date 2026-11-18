#!/usr/bin/env python3
"""Translate a YAML VM description into a QEMU command line.

The grammar is documented in docs/schema.md.  By default the generated
command is executed; use --print to inspect it and --check to validate the
configuration without running QEMU.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys

try:
    import yaml
except ImportError:
    sys.exit("yaml2qemu: error: PyYAML is required (pip install pyyaml)")

PROG = "yaml2qemu"
DEFAULT_BINARY = "qemu-system-x86_64"

ARCH_BINARIES = {
    "x86_64": "qemu-system-x86_64",
    "amd64": "qemu-system-x86_64",
    "x86": "qemu-system-i386",
    "i386": "qemu-system-i386",
    "i686": "qemu-system-i386",
    "aarch64": "qemu-system-aarch64",
    "arm64": "qemu-system-aarch64",
    "arm": "qemu-system-arm",
    "riscv64": "qemu-system-riscv64",
    "riscv32": "qemu-system-riscv32",
    "loongarch64": "qemu-system-loongarch64",
    "s390x": "qemu-system-s390x",
}

TOP_LEVEL_KEYS = {
    "binary",
    "arch",
    "machine",
    "kernel",
    "disks",
    "networks",
    "display",
    "serial",
    "monitor",
    "extra_args",
}

MACHINE_KEYS = {
    "type",
    "name",
    "cpu",
    "smp",
    "memory",
    "accel",
    "kvm",
    "nodefaults",
}

KERNEL_KEYS = {"image", "initrd", "cmdline", "dtb"}

DISK_KEYS = {
    "file",
    "format",
    "interface",
    "media",
    "readonly",
    "id",
    "boot",
    "cache",
    "discard",
    "aio",
    "werror",
    "rerror",
    "device",
    "extra",
}

NETWORK_KEYS = {"type", "id", "model", "mac", "device_extra"}

NETWORK_TYPE_KEYS = {
    "user": {
        "hostfwd",
        "tftp",
        "bootfile",
        "dns",
        "hostname",
        "domainname",
        "restrict",
        "ipv6",
        "extra",
    },
    "tap": {"ifname", "script", "downscript", "br", "helper", "extra"},
    "bridge": {"br", "helper", "extra"},
    "none": set(),
}

SCHEMA_HELP = """\
example configuration:

  arch: x86_64
  machine:
    type: q35
    cpu: max
    smp: 2
    memory: 2G
    accel: auto
  kernel:
    image: bzImage
    cmdline: root=/dev/vda rw console=ttyS0
  disks:
    - file: rootfs.ext4
      format: raw
      interface: virtio
  networks:
    - type: user
      hostfwd:
        - tcp:127.0.0.1:2222-:22
  display: none
  serial: mon:stdio
  extra_args:
    - -no-reboot

see docs/schema.md for the full grammar
"""


class ConfigError(Exception):
    """A configuration problem that should be reported to the user."""


def fail(message: str) -> None:
    """Raise a ConfigError with the given message."""
    raise ConfigError(message)


def as_mapping(value, where: str) -> dict:
    """Return value as a mapping, treating None as an empty mapping."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        fail(f"{where} must be a mapping")
    return value


def as_list(value, where: str) -> list:
    """Return value as a list, wrapping a single item and treating None as empty."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (str, int, float, dict)):
        return [value]
    fail(f"{where} must be a list")


def check_keys(mapping: dict, allowed: set, where: str) -> None:
    """Fail if mapping contains any key outside allowed."""
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        names = ", ".join(unknown)
        valid = ", ".join(sorted(allowed))
        fail(f"{where}: unknown key(s): {names} (allowed: {valid})")


def scalar(value) -> str:
    """Render a YAML scalar using QEMU's on/off spelling for booleans."""
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value)


def select_binary(cfg: dict) -> str:
    """Return the QEMU binary from binary/arch, falling back to the default."""
    if cfg.get("binary"):
        return str(cfg["binary"])

    arch = cfg.get("arch")
    if arch is None:
        return DEFAULT_BINARY

    key = str(arch).lower()
    if key not in ARCH_BINARIES:
        fail(f"arch: unsupported architecture '{arch}'")
    return ARCH_BINARIES[key]


def machine_args(cfg: dict) -> list:
    """Translate the machine section into QEMU arguments."""
    machine = cfg["machine"]
    if machine is None:
        return []
    if isinstance(machine, str):
        machine = {"type": machine}
    machine = as_mapping(machine, "machine")
    check_keys(machine, MACHINE_KEYS, "machine")

    if "accel" in machine and "kvm" in machine:
        fail("machine: use either 'accel' or 'kvm', not both")

    def accel_args(value) -> list:
        """Expand one or more accelerator values into -accel arguments."""
        values = value if isinstance(value, list) else [value]
        args = []
        for item in values:
            item = str(item).lower()
            if item == "auto":
                args += ["-accel", "kvm", "-accel", "tcg"]
            else:
                args += ["-accel", item]
        return args

    handlers = {
        "nodefaults": lambda value: ["-nodefaults"] if value else [],
        "name": lambda value: ["-name", scalar(value)],
        "type": lambda value: ["-machine", scalar(value)],
        "accel": accel_args,
        "cpu": lambda value: ["-cpu", scalar(value)],
        "smp": lambda value: ["-smp", scalar(value)],
        "memory": lambda value: ["-m", scalar(value)],
    }

    values = dict(machine)
    if values.get("accel") is None and "kvm" in values:
        values["accel"] = "kvm" if values["kvm"] else "tcg"

    args = []
    for key, handler in handlers.items():
        if values.get(key) is not None:
            args += handler(values[key])
    return args


def kernel_args(cfg: dict) -> list:
    """Translate the kernel section into QEMU arguments."""
    kernel = cfg["kernel"]
    if kernel is None:
        return []
    if isinstance(kernel, str):
        kernel = {"image": kernel}

    kernel = as_mapping(kernel, "kernel")
    check_keys(kernel, KERNEL_KEYS, "kernel")

    handlers = {
        "image": lambda value: ["-kernel", scalar(value)],
        "initrd": lambda value: ["-initrd", scalar(value)],
        "cmdline": lambda value: ["-append", scalar(value)],
        "dtb": lambda value: ["-dtb", scalar(value)],
    }

    args = []
    for key, handler in handlers.items():
        if kernel.get(key) is not None:
            args += handler(kernel[key])
    return args


def disk_options(disk: dict, where: str) -> str:
    """Build the comma-separated -drive options for a single disk."""
    def option(key):
        """Return a handler that emits key=value for a drive option."""
        return lambda value: f"{key}={scalar(value)}"

    handlers = {
        "interface": lambda value: f"if={scalar(value)}",
        "media": option("media"),
        "readonly": lambda value: "readonly=on" if value else None,
        "id": option("id"),
        "boot": lambda value: "boot=on" if value else None,
        "cache": option("cache"),
        "discard": option("discard"),
        "aio": option("aio"),
        "werror": option("werror"),
        "rerror": option("rerror"),
    }

    options = [f"file={disk['file']}", f"format={disk.get('format', 'raw')}"]
    for key, handler in handlers.items():
        if disk.get(key) is not None:
            value = handler(disk[key])
            if value is not None:
                options.append(value)
    options += [str(extra) for extra in as_list(disk.get("extra"), f"{where}.extra")]
    return ",".join(options)


def disk_entry(disk, index: int) -> list:
    """Translate one disk entry into -drive/-device arguments."""
    where = f"disks[{index}]"
    if isinstance(disk, str):
        disk = {"file": disk}
    disk = as_mapping(disk, where)
    check_keys(disk, DISK_KEYS, where)

    if not disk.get("file"):
        fail(f"{where}: 'file' is required")

    args = ["-drive", disk_options(disk, where)]
    if disk.get("device") is not None:
        args += ["-device", scalar(disk["device"])]
    return args


def disk_args(cfg: dict) -> list:
    """Translate every entry in the disks section."""
    args = []
    for index, disk in enumerate(as_list(cfg["disks"], "disks")):
        args += disk_entry(disk, index)
    return args


def network_options(network: dict, kind: str, netdev_id: str, where: str) -> str:
    """Build the comma-separated -netdev options for a single network."""
    def key_values(keys) -> list:
        """Render the present keys among keys as key=value fragments."""
        return [
            f"{key}={scalar(network[key])}"
            for key in keys
            if network.get(key) is not None
        ]

    per_type = {
        "user": lambda: [
            f"hostfwd={forward}"
            for forward in as_list(network.get("hostfwd"), f"{where}.hostfwd")
        ]
        + key_values(
            ("tftp", "bootfile", "dns", "hostname", "domainname", "restrict", "ipv6")
        ),
        "tap": lambda: key_values(
            ("ifname", "script", "downscript", "br", "helper")
        ),
        "bridge": lambda: key_values(("br", "helper")),
    }

    options = [kind, f"id={netdev_id}"]
    options += per_type[kind]()
    options += [str(extra) for extra in as_list(network.get("extra"), f"{where}.extra")]
    return ",".join(options)


def network_device(network: dict, netdev_id: str, where: str) -> list:
    """Build the -device arguments for a network's NIC."""
    model = scalar(network.get("model", "virtio-net-pci"))
    if model == "none":
        return []

    device = [model, f"netdev={netdev_id}"]
    if network.get("mac") is not None:
        device.append(f"mac={scalar(network['mac'])}")
    device += [
        str(extra)
        for extra in as_list(network.get("device_extra"), f"{where}.device_extra")
    ]
    return ["-device", ",".join(device)]


def network_entry(network, index: int) -> list:
    """Translate one network entry into -netdev/-device arguments."""
    where = f"networks[{index}]"
    if isinstance(network, str):
        network = {"type": network}
    network = as_mapping(network, where)

    kind = str(network.get("type", "user")).lower()
    if kind not in NETWORK_TYPE_KEYS:
        fail(f"{where}: unsupported network type '{kind}'")

    if kind == "none":
        check_keys(network, {"type"}, where)
        return ["-nic", "none"]

    check_keys(network, NETWORK_KEYS | NETWORK_TYPE_KEYS[kind], where)
    netdev_id = scalar(network.get("id", f"net{index}"))

    args = ["-netdev", network_options(network, kind, netdev_id, where)]
    args += network_device(network, netdev_id, where)
    return args


def network_args(cfg: dict) -> list:
    """Translate every entry in the networks section."""
    args = []
    for index, network in enumerate(as_list(cfg["networks"], "networks")):
        args += network_entry(network, index)
    return args


def console_args(cfg: dict) -> list:
    """Translate display/serial/monitor settings into QEMU arguments."""
    def option(flag, when_true, when_false):
        """Return a handler mapping booleans to flag values; None means omit."""
        def handler(value) -> list:
            """Render one console setting as QEMU arguments."""
            if value is True:
                return [flag, when_true] if when_true is not None else []
            if value is False:
                return [flag, when_false] if when_false is not None else []
            return [flag, scalar(value)]

        return handler

    handlers = {
        "display": option("-display", None, "none"),
        "serial": option("-serial", "mon:stdio", None),
        "monitor": option("-monitor", "stdio", None),
    }

    args = []
    for key, handler in handlers.items():
        if cfg.get(key) is not None:
            args += handler(cfg[key])
    return args


def extra_args(cfg: dict) -> list:
    """Return the raw extra_args values as an argument list."""
    extras = cfg["extra_args"]
    if isinstance(extras, str):
        return shlex.split(extras)
    return [str(extra) for extra in as_list(extras, "extra_args")]


def build_command(cfg: dict) -> list:
    """Translate a full configuration mapping into a QEMU command."""
    if not isinstance(cfg, dict):
        fail("configuration must be a mapping")
    check_keys(cfg, TOP_LEVEL_KEYS, "configuration")

    sections = [
        ({"machine"}, machine_args),
        ({"kernel"}, kernel_args),
        ({"disks"}, disk_args),
        ({"networks"}, network_args),
        ({"display", "serial", "monitor"}, console_args),
        ({"extra_args"}, extra_args),
    ]

    command = [select_binary(cfg)]
    for keys, section in sections:
        if keys & cfg.keys():
            command += section(cfg)
    return command


def make_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Turn a YAML VM description into QEMU parameters.",
        epilog=SCHEMA_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "config",
        nargs="?",
        default="qemu.yml",
        help="YAML configuration file (default: qemu.yml)",
    )
    parser.add_argument(
        "-p",
        "--print",
        dest="print_command",
        action="store_true",
        help="print the QEMU command instead of running it",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate the configuration, then exit",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="show the command line before running QEMU",
    )
    return parser


def load_config(path: str) -> dict:
    """Load and parse a YAML configuration file."""
    with open(path, "r", encoding="utf-8") as handle:
        try:
            cfg = yaml.safe_load(handle)
        except yaml.YAMLError as error:
            fail(f"invalid YAML: {error}")
    if cfg is None:
        fail("configuration is empty")
    return cfg


def execute(command: list) -> int:
    """Run the QEMU command and return its exit status."""
    try:
        return subprocess.run(command).returncode
    except KeyboardInterrupt:
        return 130
    except OSError as error:
        print(f"{PROG}: error: cannot run '{command[0]}': {error}", file=sys.stderr)
        return 127


def main(argv=None) -> int:
    """Run the CLI and return the process exit status."""
    options = make_parser().parse_args(argv)

    try:
        cfg = load_config(options.config)
        command = build_command(cfg)
    except (ConfigError, OSError) as error:
        print(f"{PROG}: error: {error}", file=sys.stderr)
        return 2

    if options.print_command:
        print(shlex.join(command))

    if options.check:
        print(f"{PROG}: configuration OK", file=sys.stderr)
        return 0

    if not options.print_command:
        if options.verbose:
            print(shlex.join(command), file=sys.stderr)
        return execute(command)

    return 0


if __name__ == "__main__":
    sys.exit(main())
