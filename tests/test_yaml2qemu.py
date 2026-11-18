import shlex
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import yaml2qemu


def build(cfg):
    return yaml2qemu.build_command(cfg)


def options(cfg):
    return yaml2qemu.build_command(cfg)[1:]


def run_cli(argv, capsys):
    rc = yaml2qemu.main(list(argv))
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def write_config(directory, cfg):
    path = directory / "qemu.yml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture
def full_cfg():
    return {
        "arch": "arm64",
        "machine": {
            "name": "test-vm",
            "nodefaults": True,
            "cpu": "cortex-a57",
            "smp": 4,
            "memory": "1G",
            "kvm": False,
        },
        "kernel": {
            "image": "vmlinuz",
            "initrd": "initrd.img",
            "cmdline": "console=ttyAMA0 root=/dev/vda",
            "dtb": "test.dtb",
        },
        "disks": [
            {
                "file": "rootfs.ext4",
                "format": "qcow2",
                "interface": "virtio",
                "media": "disk",
                "readonly": True,
                "id": "root",
                "boot": True,
                "cache": "writeback",
                "discard": "unmap",
                "aio": "native",
                "werror": "stop",
                "rerror": "report",
                "extra": ["snapshot=off"],
                "device": "virtio-blk-pci",
            },
            {"file": "data.ext4", "media": "cdrom"},
        ],
        "networks": [
            {
                "type": "user",
                "id": "n0",
                "model": "e1000",
                "mac": "52:54:00:12:34:56",
                "hostfwd": ["tcp::2222-:22"],
                "tftp": "tftpdir",
                "bootfile": "pxelinux.0",
                "dns": "10.0.2.3",
                "hostname": "vm",
                "domainname": "example.org",
                "restrict": True,
                "ipv6": False,
                "extra": ["dhcpstart=10.0.2.20"],
                "device_extra": ["bootindex=1"],
            },
            {"type": "tap", "ifname": "tap0", "script": False, "downscript": False},
            {"type": "bridge", "br": "br0"},
            {"type": "none"},
        ],
        "display": False,
        "serial": True,
        "monitor": "stdio",
        "extra_args": "-no-reboot -snapshot",
    }


def test_full_command(full_cfg):
    assert build(full_cfg) == [
        "qemu-system-aarch64",
        "-nodefaults",
        "-name",
        "test-vm",
        "-accel",
        "tcg",
        "-cpu",
        "cortex-a57",
        "-smp",
        "4",
        "-m",
        "1G",
        "-kernel",
        "vmlinuz",
        "-initrd",
        "initrd.img",
        "-append",
        "console=ttyAMA0 root=/dev/vda",
        "-dtb",
        "test.dtb",
        "-drive",
        "file=rootfs.ext4,format=qcow2,if=virtio,media=disk,"
        "readonly=on,id=root,boot=on,cache=writeback,discard=unmap,"
        "aio=native,werror=stop,rerror=report,snapshot=off",
        "-device",
        "virtio-blk-pci",
        "-drive",
        "file=data.ext4,format=raw,media=cdrom",
        "-netdev",
        "user,id=n0,hostfwd=tcp::2222-:22,tftp=tftpdir,"
        "bootfile=pxelinux.0,dns=10.0.2.3,hostname=vm,domainname=example.org,"
        "restrict=on,ipv6=off,dhcpstart=10.0.2.20",
        "-device",
        "e1000,netdev=n0,mac=52:54:00:12:34:56,bootindex=1",
        "-netdev",
        "tap,id=net1,ifname=tap0,script=off,downscript=off",
        "-device",
        "virtio-net-pci,netdev=net1",
        "-netdev",
        "bridge,id=net2,br=br0",
        "-device",
        "virtio-net-pci,netdev=net2",
        "-nic",
        "none",
        "-display",
        "none",
        "-serial",
        "mon:stdio",
        "-monitor",
        "stdio",
        "-no-reboot",
        "-snapshot",
    ]


@pytest.mark.parametrize(
    "arch,binary",
    [
        ("x86_64", "qemu-system-x86_64"),
        ("amd64", "qemu-system-x86_64"),
        ("i386", "qemu-system-i386"),
        ("AARCH64", "qemu-system-aarch64"),
        ("arm64", "qemu-system-aarch64"),
        ("riscv64", "qemu-system-riscv64"),
        ("riscv32", "qemu-system-riscv32"),
        ("loongarch64", "qemu-system-loongarch64"),
        ("s390x", "qemu-system-s390x"),
    ],
)
def test_arch_selects_binary(arch, binary):
    assert build({"arch": arch})[0] == binary


def test_default_binary():
    assert build({})[0] == "qemu-system-x86_64"


def test_explicit_binary_overrides_arch():
    assert build({"binary": "qemu-kvm", "arch": "arm"})[0] == "qemu-kvm"


def test_unknown_arch():
    with pytest.raises(
        yaml2qemu.ConfigError, match="arch: unsupported architecture 'm68k'"
    ):
        build({"arch": "m68k"})


def test_machine_options():
    cfg = {
        "machine": {
            "nodefaults": True,
            "name": "vm",
            "type": "q35",
            "cpu": "max",
            "smp": 2,
            "memory": "2G",
            "accel": "tcg",
        }
    }
    assert options(cfg) == [
        "-nodefaults",
        "-name",
        "vm",
        "-machine",
        "q35",
        "-accel",
        "tcg",
        "-cpu",
        "max",
        "-smp",
        "2",
        "-m",
        "2G",
    ]


def test_machine_as_string():
    assert options({"machine": "q35"}) == ["-machine", "q35"]


def test_machine_null_is_ignored():
    assert options({"machine": None}) == []


def test_machine_unknown_key():
    with pytest.raises(yaml2qemu.ConfigError, match=r"machine: unknown key\(s\): nope"):
        build({"machine": {"nope": 1}})


def test_machine_must_be_a_mapping():
    with pytest.raises(yaml2qemu.ConfigError, match="machine must be a mapping"):
        build({"machine": 5})


def test_absent_machine_options_are_omitted():
    cfg = {"machine": {"accel": "tcg", "name": None, "smp": None}}
    assert options(cfg) == ["-accel", "tcg"]


def test_accel_auto():
    assert options({"machine": {"accel": "auto"}}) == [
        "-accel",
        "kvm",
        "-accel",
        "tcg",
    ]


def test_accel_list():
    assert options({"machine": {"accel": ["kvm", "tcg"]}}) == [
        "-accel",
        "kvm",
        "-accel",
        "tcg",
    ]


def test_kvm_shorthand():
    assert options({"machine": {"kvm": True}}) == ["-accel", "kvm"]
    assert options({"machine": {"kvm": False}}) == ["-accel", "tcg"]


def test_accel_and_kvm_conflict():
    with pytest.raises(
        yaml2qemu.ConfigError, match="machine: use either 'accel' or 'kvm', not both"
    ):
        build({"machine": {"accel": "kvm", "kvm": True}})


def test_kernel_as_string():
    assert build({"kernel": "vmlinuz"})[1:] == ["-kernel", "vmlinuz"]


def test_kernel_options():
    kernel = {
        "image": "vmlinuz",
        "initrd": "initrd.img",
        "cmdline": "console=ttyS0",
        "dtb": "test.dtb",
    }
    assert build({"kernel": kernel})[1:] == [
        "-kernel",
        "vmlinuz",
        "-initrd",
        "initrd.img",
        "-append",
        "console=ttyS0",
        "-dtb",
        "test.dtb",
    ]


def test_kernel_null_is_ignored():
    assert options({"kernel": None}) == []


def test_kernel_unknown_key():
    with pytest.raises(yaml2qemu.ConfigError, match=r"kernel: unknown key\(s\): nope"):
        build({"kernel": {"nope": 1}})


def test_kernel_must_be_a_mapping():
    with pytest.raises(yaml2qemu.ConfigError, match="kernel must be a mapping"):
        build({"kernel": 5})


def test_disk_as_string():
    assert options({"disks": ["rootfs.ext4"]}) == [
        "-drive",
        "file=rootfs.ext4,format=raw",
    ]


def test_disk_options():
    cfg = {
        "disks": [
            {
                "file": "rootfs.ext4",
                "format": "qcow2",
                "interface": "nvme",
                "media": "cdrom",
                "readonly": True,
                "id": "cd0",
                "boot": True,
                "cache": "none",
                "discard": "unmap",
                "aio": "threads",
                "werror": "enospc",
                "rerror": "ignore",
            }
        ]
    }
    expected = (
        "file=rootfs.ext4,format=qcow2,if=nvme,media=cdrom,readonly=on,"
        "id=cd0,boot=on,cache=none,discard=unmap,aio=threads,werror=enospc,rerror=ignore"
    )
    assert options(cfg) == ["-drive", expected]


def test_disk_extra_and_device():
    cfg = {
        "disks": [
            {
                "file": "rootfs.ext4",
                "extra": ["detect-zeroes=unmap"],
                "device": "virtio-blk-pci",
            }
        ]
    }
    assert options(cfg) == [
        "-drive",
        "file=rootfs.ext4,format=raw,detect-zeroes=unmap",
        "-device",
        "virtio-blk-pci",
    ]


def test_disk_requires_file():
    with pytest.raises(yaml2qemu.ConfigError, match="disks\\[0\\]: 'file' is required"):
        build({"disks": [{"format": "raw"}]})


def test_disk_entry_must_be_a_mapping():
    with pytest.raises(yaml2qemu.ConfigError, match="disks\\[0\\] must be a mapping"):
        build({"disks": [5]})


def test_disk_unknown_key():
    with pytest.raises(
        yaml2qemu.ConfigError, match=r"disks\[0\]: unknown key\(s\): nope"
    ):
        build({"disks": [{"file": "x", "nope": 1}]})


def test_user_network_defaults():
    assert options({"networks": [{}]}) == [
        "-netdev",
        "user,id=net0",
        "-device",
        "virtio-net-pci,netdev=net0",
    ]


def test_network_as_string():
    assert options({"networks": ["user"]}) == [
        "-netdev",
        "user,id=net0",
        "-device",
        "virtio-net-pci,netdev=net0",
    ]


def test_user_network_options():
    cfg = {
        "networks": [
            {
                "type": "user",
                "id": "n0",
                "model": "e1000",
                "mac": "52:54:00:12:34:56",
                "hostfwd": ["tcp::2222-:22", "udp::5353-:53"],
                "tftp": "tftpdir",
                "bootfile": "pxelinux.0",
                "dns": "10.0.2.3",
                "hostname": "vm",
                "domainname": "example.org",
                "restrict": False,
                "ipv6": True,
                "extra": ["dhcpstart=10.0.2.20"],
                "device_extra": ["bootindex=2"],
            }
        ]
    }
    netdev = (
        "user,id=n0,hostfwd=tcp::2222-:22,hostfwd=udp::5353-:53,tftp=tftpdir,"
        "bootfile=pxelinux.0,dns=10.0.2.3,hostname=vm,domainname=example.org,"
        "restrict=off,ipv6=on,dhcpstart=10.0.2.20"
    )
    device = "e1000,netdev=n0,mac=52:54:00:12:34:56,bootindex=2"
    assert options(cfg) == ["-netdev", netdev, "-device", device]


def test_tap_network():
    cfg = {
        "networks": [
            {
                "type": "tap",
                "ifname": "tap0",
                "script": False,
                "downscript": False,
                "br": "br0",
                "helper": "/usr/lib/qemu-bridge-helper",
            }
        ]
    }
    assert options(cfg) == [
        "-netdev",
        "tap,id=net0,ifname=tap0,script=off,downscript=off,br=br0,"
        "helper=/usr/lib/qemu-bridge-helper",
        "-device",
        "virtio-net-pci,netdev=net0",
    ]


def test_bridge_network():
    cfg = {"networks": [{"type": "bridge", "br": "br0"}]}
    assert options(cfg) == [
        "-netdev",
        "bridge,id=net0,br=br0",
        "-device",
        "virtio-net-pci,netdev=net0",
    ]


def test_network_none():
    assert options({"networks": [{"type": "none"}]}) == ["-nic", "none"]


def test_network_none_rejects_extra_keys():
    with pytest.raises(yaml2qemu.ConfigError, match=r"networks\[0\]: unknown key"):
        build({"networks": [{"type": "none", "id": "n0"}]})


def test_network_model_none_omits_device():
    assert options({"networks": [{"type": "user", "model": "none"}]}) == [
        "-netdev",
        "user,id=net0",
    ]


def test_network_ids_use_list_index_past_none():
    cfg = {"networks": [{"type": "tap"}, {"type": "none"}, "user"]}
    assert options(cfg) == [
        "-netdev",
        "tap,id=net0",
        "-device",
        "virtio-net-pci,netdev=net0",
        "-nic",
        "none",
        "-netdev",
        "user,id=net2",
        "-device",
        "virtio-net-pci,netdev=net2",
    ]


def test_network_unknown_type():
    with pytest.raises(
        yaml2qemu.ConfigError, match="networks\\[0\\]: unsupported network type 'socket'"
    ):
        build({"networks": [{"type": "socket"}]})


def test_network_unknown_key_for_type():
    with pytest.raises(
        yaml2qemu.ConfigError, match=r"networks\[0\]: unknown key\(s\): br"
    ):
        build({"networks": [{"type": "user", "br": "br0"}]})


def test_display():
    assert options({"display": "none"}) == ["-display", "none"]
    assert options({"display": False}) == ["-display", "none"]
    assert options({"display": True}) == []
    assert options({"display": None}) == []


def test_serial():
    assert options({"serial": True}) == ["-serial", "mon:stdio"]
    assert options({"serial": "telnet:127.0.0.1:4444,server"}) == [
        "-serial",
        "telnet:127.0.0.1:4444,server",
    ]
    assert options({"serial": False}) == []
    assert options({"serial": None}) == []


def test_monitor():
    assert options({"monitor": True}) == ["-monitor", "stdio"]
    assert options({"monitor": "unix:mon.sock,server,nowait"}) == [
        "-monitor",
        "unix:mon.sock,server,nowait",
    ]
    assert options({"monitor": False}) == []
    assert options({"monitor": None}) == []


def test_extra_args():
    assert options({"extra_args": ["-no-reboot", "-snapshot"]}) == [
        "-no-reboot",
        "-snapshot",
    ]
    assert options({"extra_args": "-no-reboot -snapshot"}) == [
        "-no-reboot",
        "-snapshot",
    ]
    assert options({"extra_args": [42]}) == ["42"]
    assert options({}) == []


@pytest.mark.parametrize(
    "value,expected",
    [(True, "on"), (False, "off"), (5, "5"), ("x", "x")],
)
def test_scalar(value, expected):
    assert yaml2qemu.scalar(value) == expected


def test_as_list():
    assert yaml2qemu.as_list(None, "x") == []
    assert yaml2qemu.as_list([1, 2], "x") == [1, 2]
    assert yaml2qemu.as_list("a", "x") == ["a"]
    with pytest.raises(yaml2qemu.ConfigError, match="x must be a list"):
        yaml2qemu.as_list({1, 2}, "x")


def test_as_mapping():
    assert yaml2qemu.as_mapping(None, "x") == {}
    assert yaml2qemu.as_mapping({"a": 1}, "x") == {"a": 1}
    with pytest.raises(yaml2qemu.ConfigError, match="x must be a mapping"):
        yaml2qemu.as_mapping(5, "x")


def test_unknown_top_level_key():
    with pytest.raises(
        yaml2qemu.ConfigError, match=r"configuration: unknown key\(s\): nope"
    ):
        build({"nope": 1})


def test_configuration_must_be_a_mapping():
    with pytest.raises(yaml2qemu.ConfigError, match="configuration must be a mapping"):
        build(["a", "b"])


def test_cli_print(tmp_path, full_cfg, capsys):
    path = write_config(tmp_path, full_cfg)
    rc, out, err = run_cli(["-p", str(path)], capsys)
    assert rc == 0
    assert err == ""
    assert out == shlex.join(build(full_cfg)) + "\n"


def test_cli_check_ok(tmp_path, capsys):
    path = write_config(tmp_path, {"machine": "q35"})
    rc, out, err = run_cli(["--check", str(path)], capsys)
    assert rc == 0
    assert out == ""
    assert err == "yaml2qemu: configuration OK\n"


def test_cli_check_reports_errors(tmp_path, capsys):
    path = write_config(tmp_path, {"nope": 1})
    rc, out, err = run_cli(["--check", str(path)], capsys)
    assert rc == 2
    assert "unknown key" in err


def test_cli_check_and_print(tmp_path, full_cfg, capsys):
    path = write_config(tmp_path, full_cfg)
    rc, out, err = run_cli(["--check", "-p", str(path)], capsys)
    assert rc == 0
    assert out == shlex.join(build(full_cfg)) + "\n"
    assert err == "yaml2qemu: configuration OK\n"


def test_cli_default_config_file(tmp_path, monkeypatch, capsys):
    write_config(tmp_path, {"machine": "q35"})
    monkeypatch.chdir(tmp_path)
    rc, out, err = run_cli(["-p"], capsys)
    assert rc == 0
    assert out == "qemu-system-x86_64 -machine q35\n"


def test_cli_missing_config(tmp_path, capsys):
    rc, out, err = run_cli(["-p", str(tmp_path / "nope.yml")], capsys)
    assert rc == 2
    assert "No such file or directory" in err


def test_cli_invalid_yaml(tmp_path, capsys):
    path = tmp_path / "bad.yml"
    path.write_text("a: [1,\n", encoding="utf-8")
    rc, out, err = run_cli(["-p", str(path)], capsys)
    assert rc == 2
    assert err.startswith("yaml2qemu: error: invalid YAML:")


def test_cli_empty_config(tmp_path, capsys):
    path = tmp_path / "empty.yml"
    path.write_text("", encoding="utf-8")
    rc, out, err = run_cli(["-p", str(path)], capsys)
    assert rc == 2
    assert err == "yaml2qemu: error: configuration is empty\n"


def test_cli_config_not_a_mapping(tmp_path, capsys):
    path = tmp_path / "list.yml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    rc, out, err = run_cli(["-p", str(path)], capsys)
    assert rc == 2
    assert err == "yaml2qemu: error: configuration must be a mapping\n"


def test_cli_help(capsys):
    with pytest.raises(SystemExit) as excinfo:
        yaml2qemu.main(["--help"])
    out = capsys.readouterr().out
    assert excinfo.value.code == 0
    assert out.startswith("usage: yaml2qemu")
    assert "docs/schema.md" in out


def test_cli_verbose_run(monkeypatch, tmp_path, capsys):
    calls = []

    def fake_run(command):
        calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(yaml2qemu.subprocess, "run", fake_run)
    path = write_config(tmp_path, {"binary": "/bin/true"})
    rc, out, err = run_cli(["-v", str(path)], capsys)
    assert rc == 0
    assert out == ""
    assert err == "/bin/true\n"
    assert calls == [["/bin/true"]]


def test_cli_run_returns_exit_code(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        yaml2qemu.subprocess, "run", lambda command: SimpleNamespace(returncode=1)
    )
    path = write_config(tmp_path, {"binary": "/bin/true"})
    rc, out, err = run_cli([str(path)], capsys)
    assert rc == 1
    assert out == ""
    assert err == ""


def test_cli_keyboard_interrupt(monkeypatch, tmp_path, capsys):
    def interrupt(command):
        raise KeyboardInterrupt

    monkeypatch.setattr(yaml2qemu.subprocess, "run", interrupt)
    path = write_config(tmp_path, {"binary": "/bin/true"})
    rc, out, err = run_cli([str(path)], capsys)
    assert rc == 130


def test_cli_binary_not_found(monkeypatch, tmp_path, capsys):
    def missing(command):
        raise FileNotFoundError(f"[Errno 2] No such file or directory: '{command[0]}'")

    monkeypatch.setattr(yaml2qemu.subprocess, "run", missing)
    path = write_config(tmp_path, {})
    rc, out, err = run_cli([str(path)], capsys)
    assert rc == 127
    assert "cannot run 'qemu-system-x86_64'" in err


def test_example_config_prints_expected_command(capsys):
    config = Path(__file__).resolve().parent.parent / "examples" / "qemu.yml"
    rc, out, err = run_cli(["-p", str(config)], capsys)
    assert rc == 0
    assert err == ""
    assert out == shlex.join(
        [
            "qemu-system-x86_64",
            "-nodefaults",
            "-name",
            "tiny-horse",
            "-machine",
            "q35",
            "-accel",
            "kvm",
            "-accel",
            "tcg",
            "-cpu",
            "max",
            "-smp",
            "2",
            "-m",
            "512M",
            "-kernel",
            "../build/tmp/deploy/images/qemux86-64/bzImage",
            "-append",
            "root=/dev/vda rw console=ttyS0",
            "-drive",
            "file=../build/tmp/deploy/images/qemux86-64/"
            "tiny-horse-image-qemux86-64.rootfs.ext4,"
            "format=raw,if=virtio,cache=writeback",
            "-netdev",
            "user,id=net0,hostfwd=tcp:127.0.0.1:2222-:22,hostfwd=tcp:127.0.0.1:8000-:8000",
            "-device",
            "virtio-net-pci,netdev=net0",
            "-display",
            "none",
            "-serial",
            "mon:stdio",
            "-no-reboot",
        ]
    ) + "\n"
