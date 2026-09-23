{
  description = "Saturnino anime media workflow development shell";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forEachSystem = nixpkgs.lib.genAttrs systems;
    in {
      devShells = forEachSystem (system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python3.withPackages (ps: with ps; [
            httpx
            mypy
            playwright
            pytest
          ]);
        in {
          default = pkgs.mkShell {
            packages = [
              python
              pkgs.chromium
              pkgs.ffmpeg
              pkgs.mpv
              pkgs.ruff
            ];
            env.CHROMIUM_EXECUTABLE_PATH = "${pkgs.chromium}/bin/chromium";
            shellHook = ''
              export PYTHONPATH="$PWD''${PYTHONPATH:+:$PYTHONPATH}"
              echo "saturnino dev shell"
              echo "Run: python main.py \"Chainsmoker Cat\""
            '';
          };
        });
    };
}
