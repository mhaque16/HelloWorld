"""Per-user macOS launchd scheduling, activated only from Enable in the app."""
import hashlib
import os
import plistlib
import subprocess
from pathlib import Path


def label_for(root):
    return 'com.dunkinpriceagent.' + hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:10]


def launch_agent(root, time_text):
    from .agent import schedule_command
    schedule_command(root, time_text)  # Shared strict HH:MM validation.
    hour, minute = map(int, time_text.split(':'))
    return {
        'Label': label_for(root),
        'ProgramArguments': [str(root.resolve() / '.venv/bin/python'), '-X', 'utf8', '-m', 'dunkin_compare.agent', 'run'],
        'WorkingDirectory': str(root.resolve()),
        'StartCalendarInterval': {'Hour': hour, 'Minute': minute},
        'RunAtLoad': False,
        'StandardOutPath': str(root.resolve() / 'logs/scheduler_stdout.txt'),
        'StandardErrorPath': str(root.resolve() / 'logs/scheduler_stderr.txt'),
    }


def configure(root, time_text, remove=False):
    from .training import atomic_json
    # Resolves the actual Mac user's home at runtime; no privileged/system daemon.
    path = Path.home() / 'Library/LaunchAgents' / (label_for(root) + '.plist')
    configuration = None
    if not remove:
        if not (root / '.venv/bin/python').is_file():
            raise RuntimeError('Run Setup Mac.command before enabling the schedule.')
        configuration = launch_agent(root, time_text)
    domain = f'gui/{os.getuid()}'
    target = domain + '/' + label_for(root)
    def run(arguments):
        return subprocess.run(['/bin/launchctl', *arguments], capture_output=True, text=True, timeout=20)
    found = run(['print', target])
    if found.returncode not in (0, 113):
        raise RuntimeError(found.stderr.strip() or 'macOS could not inspect the existing schedule.')
    if found.returncode == 0:
        result = run(['bootout', target])
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or 'macOS could not stop the previous daily schedule.')
    if remove:
        path.unlink(missing_ok=True)
        atomic_json(root / 'local_state/schedule.json', {'enabled': False, 'time': time_text})
        return
    (root / 'logs').mkdir(exist_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.plist.tmp')
    temporary.write_bytes(plistlib.dumps(configuration))
    os.replace(temporary, path)
    result = run(['bootstrap', domain, str(path)])
    if result.returncode:
        atomic_json(root / 'local_state/schedule.json', {'enabled': False, 'time': time_text})
        raise RuntimeError(result.stderr.strip() or 'macOS could not load the daily schedule. Check System Settings > General > Login Items.')
    atomic_json(root / 'local_state/schedule.json', {'enabled': True, 'time': time_text})
