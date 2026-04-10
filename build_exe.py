import subprocess
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PYTHON = sys.executable

def run(cmd, cwd=None):
    print("\n> Running:", " ".join(cmd))
    print("  (cwd:", cwd or str(ROOT), ")")
    subprocess.run(cmd, cwd=cwd, check=True)

def main():
    print("Using Python interpreter:", PYTHON)

    # 2) Prepare for main.spec: clean old dist/Serial if needed
    dist_serial = ROOT / "dist" / "WHATControlCenter"
    if dist_serial.exists():
        print(f"Removing existing output directory: {dist_serial}")
        shutil.rmtree(dist_serial)

    # 3) Build main exe from spec, also with -y
    run(
        [
            PYTHON,
            "-m", "PyInstaller",
            "--clean",
            "-y",                # overwrite output dir without asking
            "main.spec",
        ],
        cwd=ROOT,
    )

    # 4) Optional: Build installer with Inno Setup (command-line compiler)
    inno_compiler = r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
    iss_script = "inno_setup_script_for_making_installer.iss"

    run(
        [inno_compiler, iss_script],
        cwd=ROOT,
    )

    # 5) Open Explorer at output directory
    output_folder = ROOT / "Output"
    print(f"\nOpening Explorer at: {output_folder}")
    subprocess.Popen(["explorer", str(output_folder)])


if __name__ == "__main__":
    main()