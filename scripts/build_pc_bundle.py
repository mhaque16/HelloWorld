"""Create a source-only Windows-friendly distribution without local state."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent.parent
TOP_FILES = ['README.md', 'START_HERE.txt', 'requirements.txt', '.gitignore',
             'setup_windows.bat', 'run_windows.bat', 'demo_windows.bat', 'open_agent.bat', 'run_scheduled.bat']
DIRECTORIES = ['dunkin_compare', 'config', 'data', 'tests', 'scripts']
files = [ROOT / filename for filename in TOP_FILES]
for directory in DIRECTORIES:
    files.extend(path for path in (ROOT / directory).rglob('*')
                 if path.is_file() and '__pycache__' not in path.parts
                 and path.suffix in ('.py', '.js', '.json', '.csv', '.html'))
target = ROOT / 'dist/DunkinPriceAgent-PC.zip'
target.parent.mkdir(exist_ok=True)
with ZipFile(target, 'w', compression=ZIP_DEFLATED) as archive:
    for path in sorted(files):
        relative = path.relative_to(ROOT)
        if not path.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError(f'Cannot bundle a path outside the project: {relative}')
        data = path.read_bytes()
        if path.suffix == '.bat':
            data = data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
        archive.writestr('DunkinPriceCompare/' + relative.as_posix(), data)
print(target)
