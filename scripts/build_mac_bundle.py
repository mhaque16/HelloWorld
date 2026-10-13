"""Mac ZIP with executable Finder launchers and no local browser/session state."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parent.parent
files = [ROOT / name for name in ['README.md', 'START_HERE_MAC.txt', 'requirements.txt', '.gitignore',
                                 'Setup Mac.command', 'Open Agent Mac.command', 'Prepare Free AI Mac.command']]
for directory in ['dunkin_compare', 'config', 'data', 'tests', 'scripts']:
    files.extend(p for p in (ROOT / directory).rglob('*') if p.is_file()
                 and '__pycache__' not in p.parts and p.suffix in ('.py', '.js', '.json', '.csv', '.html'))
target = ROOT / 'dist/DunkinPriceAgent-Mac.zip'
target.parent.mkdir(exist_ok=True)
with ZipFile(target, 'w', compression=ZIP_DEFLATED) as archive:
    for path in sorted(files):
        if not path.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError('Cannot bundle a file outside the project')
        info = ZipInfo('DunkinPriceAgent/' + path.relative_to(ROOT).as_posix())
        info.create_system = 3
        info.compress_type = ZIP_DEFLATED
        info.external_attr = ((0o100755 if path.suffix == '.command' else 0o100644) << 16)
        archive.writestr(info, path.read_bytes())
print(target)
