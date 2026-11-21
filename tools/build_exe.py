"""一键构建双击可玩的 Windows exe（PyInstaller onefile）。

发布工程专用入口：只编排打包，不改任何 G0–G7 已验收模块；三张表与
MANIFEST 以只读数据文件方式打进包，golden 快照与测试不打进发行包。

用法：
  python tools/build_exe.py              # 构建到 dist/PokeWorld.exe
  python tools/build_exe.py --name X     # 自定义 exe 名

产物体积来自 Python 运行时 + pygame；构建过程零改源码 / 零改表。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_TEMPLATE = '''# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
hidden = collect_submodules("src") + ["autoplayer", "g5_report", "ow_report"]

a = Analysis(
    ["{launcher}"],
    pathex=["{root}"],
    binaries=[],
    datas=[
        ("{root}/data/topology.json", "data"),
        ("{root}/data/species.json", "data"),
        ("{root}/data/encounters.json", "data"),
        ("{root}/data/MANIFEST.sha256", "data"),
        ("{root}/tests/golden_seed.json", "tests"),
    ],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pytest", "unittest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="{name}",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
'''


def build(name: str) -> int:
    """生成临时 spec、调用 PyInstaller，返回其退出码。"""
    build_dir = ROOT / "build"
    build_dir.mkdir(exist_ok=True)
    spec = build_dir / "PokeWorld.build.spec"
    spec.write_text(
        SPEC_TEMPLATE.format(
            launcher=(ROOT / "tools" / "launcher.py").as_posix(),
            root=ROOT.as_posix(),
            name=name,
        ),
        encoding="utf-8",
    )
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
               "--distpath", str(ROOT / "dist"),
               "--workpath", str(ROOT / "build"),
               str(spec)]
    result = subprocess.run(command, cwd=str(ROOT), check=False)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="构建双击可玩的 PokeWorld exe")
    parser.add_argument("--name", default="PokeWorld", help="exe 名称（不含扩展名）")
    args = parser.parse_args()
    code = build(args.name)
    if code == 0:
        exe = ROOT / "dist" / f"{args.name}.exe"
        print(f"BUILD OK -> {exe} ({exe.stat().st_size} bytes)")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
