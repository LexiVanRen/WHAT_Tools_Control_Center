import subprocess
from pathlib import Path

PADEN = [
    r"C:\Users\ABC-RnD\Documents\GitHub\DriveDoctor_Tool",
    r"C:\Users\ABC-RnD\Documents\GitHub\Ethernet",
    r"C:\Users\ABC-RnD\Documents\GitHub\Serial",
    r"C:\Users\ABC-RnD\Documents\GitHub\JTAG",
    r"C:\Users\ABC-RnD\Documents\GitHub\Profibus_Tool",
    r"C:\Users\ABC-RnD\Documents\GitHub\WHAT_app_template",
    r"C:\Users\ABC-RnD\Documents\GitHub\Touchscreen",
    r"C:\Users\ABC-RnD\Documents\GitHub\SRAM_Tool",
    r"C:\Users\ABC-RnD\PycharmProjects\CAN",
]

SUBMODULE = "WHAT_Tools_Event_logger"
CMD = ["git", "submodule", "update", "--remote", SUBMODULE]

for p_str in PADEN:
    p = Path(p_str)
    if not p.is_dir():
        print(f"⚠️  Skipping (not a directory): {p}")
        continue

    print(f"Running in: {p}")
    try:
        result = subprocess.run(
            CMD,
            cwd=p,
            check=True,
            text=True,
            capture_output=True,
        )
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error in {p}:")
        print(e.stdout)
        print(e.stderr)