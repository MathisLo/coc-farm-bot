"""Create a PyInstaller Windows version resource from app_meta.py."""
from pathlib import Path
import runpy
import sys


version = runpy.run_path(str(Path(__file__).resolve().parents[1] / "app_meta.py"))["APP_VERSION"]
parts = tuple(int(part) for part in version.split("."))
if len(parts) != 3:
    raise ValueError("APP_VERSION doit contenir trois nombres.")
parts += (0,)
target = Path(sys.argv[1])
target.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={parts}, prodvers={parts},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'CoC Farm Bot'),
    StringStruct('FileDescription', 'CoC Farm Bot'),
    StringStruct('FileVersion', '{version}'),
    StringStruct('InternalName', 'CoCFarmBot'),
    StringStruct('OriginalFilename', 'CoCFarmBot.exe'),
    StringStruct('ProductName', 'CoC Farm Bot'),
    StringStruct('ProductVersion', '{version}')
  ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
""", encoding="utf-8")
