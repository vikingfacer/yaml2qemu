# yaml2qemu

[![CI](https://github.com/vikingfacer/yaml2qemu/actions/workflows/ci.yml/badge.svg)](https://github.com/vikingfacer/yaml2qemu/actions/workflows/ci.yml) ![pipx](https://img.shields.io/badge/pipx-%232CFFAA.svg?style=for-the-badge&logo=pipx&logoColor=black) ![Nx](https://img.shields.io/badge/nx-%23143055.svg?style=for-the-badge&logo=nx&logoColor=white) ![Python](https://img.shields.io/badge/python-%233670A0.svg?style=for-the-badge&logo=python&logoColor=ffdd54)

QEMU-system commands are hard to edit, yaml is easier. Why not describe qemu system in yaml?

```yaml
arch: x86_64
machine:
  type: q35
  cpu: max
  smp: 2
  memory: 512M
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
```

```console
$ yaml2qemu vm.yml
```

By default the generated command is executed.

- `--print` — inspect the command instead of running it.
- `--check` — validate the configuration without running QEMU.
- `--verbose` — show the command before it runs.

Unknown keys are rejected so typos fail loudly; anything the grammar does
not cover can be passed through with `extra_args`.

## Installation

`yaml2qemu` is a Python application and is best installed with
[pipx](https://pipx.pypa.io/):

```console
pipx install .                                          # local checkout
pipx install git+https://github.com/vikingfacer/yaml2qemu     # from git
pipx install yaml2qemu                                  # from PyPI
```

QEMU must be installed separately; the `qemu-system-*` binary for the chosen
`arch` is looked up at runtime.

## Usage

```console
yaml2qemu [-p | --print] [--check] [-v | --verbose] [config]
```

`config` defaults to `qemu.yml`. The full YAML grammar is documented in
[docs/schema.md](docs/schema.md); a complete example lives in
[examples/qemu.yml](examples/qemu.yml).

## Development

A Nix flake provides a development shell with QEMU and the Python packages:

```console
nix develop
```

Build distribution artifacts with:

```console
python -m build
```

## License

Licensed under the [MIT License](LICENSE).
