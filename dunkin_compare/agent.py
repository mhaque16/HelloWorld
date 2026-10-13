"""One-click and scheduled jobs, with readiness checks and overlap protection."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .desktop_data import read_all

ROOT = Path(__file__).resolve().parent.parent


@contextlib.contextmanager
def job_lock(root=ROOT):
    path = root / 'local_state/agent.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        if path.stat().st_size == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('A price-collection job is already running. Finish it first.') from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def automatic_missing(root=ROOT, require_test=False):
    stores = read_all(root)
    profiles = json.loads((root / 'config/profiles.json').read_text(encoding='utf-8'))
    if not stores:
        return ['Add at least one store first.']
    ids = [s.store_id for s in stores]
    if len(ids) != len(set(ids)):
        return ['Store IDs must be unique.']
    from .ai_runner import settings
    ai=settings(root)
    if ai.get('enabled'):
        from .ai_credentials import get_key
        missing=[]
        if not get_key():
            missing.append('Open AI settings and add your API key on this computer.')
        if any(s.channel not in ('pickup','delivery') for s in stores):
            missing.append('AI web collection supports pickup and delivery, not inferred in-store prices.')
        from .ai_runner import store_signature
        if require_test and (not ai.get('last_validated_at') or ai.get('last_validated_stores')!=store_signature(stores)):
            missing.append('Run automatically now to test AI collection before scheduling.')
        return missing
    missing = []
    for store in stores:
        profile = profiles.get(store.profile, {})
        if profile.get('mode') != 'trained' or profile.get('store_id') != store.store_id or not profile.get('pages'):
            missing.append(f'Teach menu pages for {store.address}')
        elif profile.get('address') != store.address or profile.get('channel') != store.channel:
            missing.append(f'Address or pricing channel changed; teach {store.address} again')
        elif require_test and not profile.get('last_validated_at'):
            missing.append(f'Click Run automatically now to test {store.address}')
    return missing


def schedule_command(root, time_text, remove=False):
    import re
    if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', time_text):
        raise ValueError('Enter a daily time in 24-hour format, for example 09:00 or 17:30.')
    suffix = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:10]
    task = 'DunkinPriceCompare_' + suffix
    if remove:
        return ['schtasks', '/Delete', '/TN', task, '/F']
    return ['schtasks', '/Create', '/TN', task, '/XML', str(root.resolve() / 'local_state/schedule.xml'), '/F']


def schedule_xml(root, time_text, user):
    import xml.etree.ElementTree as ET
    schedule_command(root, time_text)  # Validate time before constructing a task.
    namespace = 'http://schemas.microsoft.com/windows/2004/02/mit/task'
    ET.register_namespace('', namespace)
    def element(parent, name, value=None):
        node = ET.SubElement(parent, '{'+namespace+'}'+name)
        if value is not None:
            node.text = str(value)
        return node
    task = ET.Element('{'+namespace+'}Task', version='1.2')
    triggers = element(task, 'Triggers')
    trigger = element(triggers, 'CalendarTrigger')
    element(trigger, 'StartBoundary', datetime.now().date().isoformat()+'T'+time_text+':00')
    element(trigger, 'Enabled', 'true')
    element(element(trigger, 'ScheduleByDay'), 'DaysInterval', '1')
    principal = element(element(task, 'Principals'), 'Principal')
    principal.set('id', 'CurrentUser')
    element(principal, 'UserId', user)
    element(principal, 'LogonType', 'InteractiveToken')
    element(principal, 'RunLevel', 'LeastPrivilege')
    settings = element(task, 'Settings')
    for name, value in [('MultipleInstancesPolicy', 'IgnoreNew'), ('DisallowStartIfOnBatteries', 'false'),
                        ('StopIfGoingOnBatteries', 'false'), ('StartWhenAvailable', 'true'),
                        ('ExecutionTimeLimit', 'PT1H'), ('Enabled', 'true')]:
        element(settings, name, value)
    actions = element(task, 'Actions')
    actions.set('Context', 'CurrentUser')
    execute = element(actions, 'Exec')
    element(execute, 'Command', str(root.resolve() / '.venv/Scripts/pythonw.exe'))
    element(execute, 'Arguments', '-X utf8 -m dunkin_compare.agent run')
    element(execute, 'WorkingDirectory', str(root.resolve()))
    return ET.tostring(task, encoding='utf-16', xml_declaration=True)


def configure_schedule(time_text='09:00', remove=False, root=ROOT):
    schedule_command(root, time_text)
    if sys.platform == 'darwin':
        if not remove:
            missing = automatic_missing(root, require_test=True)
            if missing:
                raise ValueError('\n'.join(missing))
        from .mac_schedule import configure
        return configure(root, time_text, remove)
    if os.name != 'nt':
        raise RuntimeError('Daily scheduling is available on Windows and macOS.')
    if not remove:
        missing = automatic_missing(root, require_test=True)
        if missing:
            raise ValueError('\n'.join(missing))
        user = subprocess.run(['whoami'], capture_output=True, text=True, check=True,
                              creationflags=subprocess.CREATE_NO_WINDOW, timeout=15).stdout.strip()
        if not user:
            raise RuntimeError('Could not identify the current Windows account for scheduling.')
        path = root / 'local_state/schedule.xml'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(schedule_xml(root, time_text, user))
    result = subprocess.run(schedule_command(root, time_text, remove), capture_output=True,
                            text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'Windows could not update the daily task.')
    from .training import atomic_json
    atomic_json(root / 'local_state/schedule.json', {'enabled': not remove, 'time': time_text})


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['guided', 'teach', 'run'])
    parser.add_argument('--store-id')
    args = parser.parse_args(argv)
    stamp = datetime.now(ZoneInfo('America/New_York')).strftime('%Y%m%d_%H%M%S_%f')
    log = ROOT / 'logs' / f'{args.command}_{stamp}.txt'
    log.parent.mkdir(exist_ok=True)
    # Logs are also echoed to the desktop application's activity panel.
    class Tee:
        def __init__(self, original, file):
            self.original, self.file = original, file
        def write(self, text):
            self.file.write(text)
            self.file.flush()
            if self.original:
                self.original.write(text)
                self.original.flush()
        def flush(self):
            self.file.flush()

    with log.open('w', encoding='utf-8') as file, contextlib.redirect_stdout(Tee(sys.stdout, file)), contextlib.redirect_stderr(Tee(sys.stderr, file)):
        try:
            with job_lock():
                if args.command == 'teach':
                    stores = [s for s in read_all(ROOT) if s.store_id == args.store_id]
                    if len(stores) != 1:
                        raise ValueError('Select exactly one store to teach.')
                    before_profiles = json.loads((ROOT / 'config/profiles.json').read_text())
                    before = before_profiles.get(stores[0].profile, {}).get('last_taught_at')
                    from .interactive import collect_interactive
                    collect_interactive(stores[0], 'auto', ROOT / 'reports/captures' / f'teaching_{stamp}.jsonl', training=True)
                    profiles = json.loads((ROOT / 'config/profiles.json').read_text())
                    current = next(s for s in read_all(ROOT) if s.store_id == args.store_id)
                    if profiles.get(current.profile, {}).get('last_taught_at') == before:
                        raise ValueError('No automatic page was taught. Use Teach autorun this page before finishing.')
                    print('Teaching saved. Click Run automatically now to test the saved pages.')
                    return 0
                from .__main__ import main as collect_main
                if args.command == 'guided':
                    return collect_main(['--interactive'])
                missing = automatic_missing()
                if missing:
                    raise ValueError('Automatic setup needs attention:\n' + '\n'.join(missing))
                from .ai_runner import settings, run
                if settings(ROOT).get('enabled'):
                    return run(ROOT)
                result = collect_main([])
                if result == 0:
                    from .training import atomic_json
                    profiles = json.loads((ROOT / 'config/profiles.json').read_text())
                    for store in read_all(ROOT):
                        profiles[store.profile]['last_validated_at'] = datetime.now(ZoneInfo('America/New_York')).isoformat()
                    atomic_json(ROOT / 'config/profiles.json', profiles)
                    print('Automatic run passed for all taught pages. Daily scheduling is now available.')
                return result
        except Exception as exc:
            print(f'Needs attention: {exc}', file=sys.stderr)
            return 1


if __name__ == '__main__':
    raise SystemExit(main())
