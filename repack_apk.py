import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def workspace_root() -> Path:
    return Path(__file__).resolve().parent


def load_jsonc(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:
            import jsonc  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Install json-with-comments") from exc
        return jsonc.loads(raw)


def normalize_arch_values(values: Iterable[str]) -> List[str]:
    out = []
    seen = set()
    for item in values:
        for part in str(item).split(","):
            a = part.strip()
            if a and a not in seen:
                seen.add(a)
                out.append(a)
    return out


def find_android_tool(tool_base_name: str) -> Optional[Path]:
    direct = shutil.which(tool_base_name)
    if direct:
        return Path(direct)

    sdk_root = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    if not sdk_root:
        return None

    build_tools = Path(sdk_root) / "build-tools"
    if not build_tools.exists():
        return None

    candidates = []
    for v in build_tools.iterdir():
        if v.is_dir():
            p = v / tool_base_name
            if p.exists():
                candidates.append(p)

    return sorted(candidates)[-1] if candidates else None


def run_cmd(args: List[str], msg: str) -> None:
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        raise RuntimeError(msg + "\n" + p.stdout)


def find_latest_apk(app_build_type: str) -> Path:
    pattern = workspace_root() / "manager" / "app" / "build" / "outputs" / "apk" / app_build_type
    apks = sorted(pattern.glob("*.apk"), key=lambda p: p.stat().st_mtime)
    if not apks:
        raise FileNotFoundError("No APK found")
    return apks[-1]


def repack_apk(apk: Path, out: Path) -> None:
    with tempfile.TemporaryDirectory() as td:
        with ZipFile(apk, "r") as zin, ZipFile(out, "w") as zout:
            for i in zin.infolist():
                data = zin.read(i.filename)
                zi = ZipInfo(i.filename)
                zi.compress_type = ZIP_DEFLATED
                zout.writestr(zi, data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--out")
    args = parser.parse_args()

    apk = find_latest_apk("debug")

    out_dir = Path(args.out or "dist")
    out_dir.mkdir(exist_ok=True)

    unsigned = out_dir / "out-unsigned.apk"
    aligned = out_dir / "out-aligned.apk"

    if unsigned.exists(): unsigned.unlink()
    if aligned.exists(): aligned.unlink()

    repack_apk(apk, unsigned)

    zipalign = find_android_tool("zipalign")
    if not zipalign:
        raise RuntimeError("zipalign not found")

    run_cmd([str(zipalign), "-P", "16", "-f", "4", str(unsigned), str(aligned)], "zipalign failed")

    print("DONE (NO SIGN):", aligned)


if __name__ == "__main__":
    main()
