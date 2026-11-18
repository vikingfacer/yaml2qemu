{
  description = "A very basic flake";

  inputs = {
    nixpkgs.url = "https://channels.nixos.org/nixpkgs-unstable/nixexprs.tar.zst";
  };

  outputs = inputs: {

    devShells = builtins.mapAttrs (system: pkgs: {

      default = pkgs.mkShell {
        packages = with pkgs; [
          python3
          python3Packages.setuptools # pkg_resources is imported at runtime
          python3Packages.kconfiglib
          python3Packages.jsonschema
          python3Packages.distro
          python3Packages.pyyaml
          python3Packages.gitpython
          python3Packages.colorlog
          python3Packages.pytest
          python3Packages.build
          qemu_full
          glow
        ];
      };
    }) inputs.nixpkgs.legacyPackages;
  };
}
