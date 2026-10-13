"""Simple local control panel. No terminals or CSV editing needed after setup."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import uuid
from dataclasses import replace
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, ttk

from .agent import ROOT, automatic_missing, configure_schedule
from .core import Store
from .desktop_data import read_all, write_group


class App:
    def __init__(self, window):
        self.window = window
        self.process = None
        self.events = queue.Queue()
        window.title('Dunkin Price Agent')
        window.geometry('860x670')
        window.minsize(740, 600)
        window.protocol('WM_DELETE_WINDOW', self.close)
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Dunkin Price Agent', font=('Segoe UI', 22, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='Compare your stores with competitors. Your Excel reports stay on this computer.').pack(anchor='w', pady=(0, 12))
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x')
        ttk.Button(buttons, text='Edit our stores', command=lambda: self.edit_stores('parent')).pack(side='left', padx=(0, 8))
        ttk.Button(buttons, text='Edit competitors', command=lambda: self.edit_stores('competitor')).pack(side='left', padx=(0, 8))
        ttk.Button(buttons, text='Open Excel reports', command=lambda: self.open_folder(ROOT / 'reports')).pack(side='left')
        ttk.Button(buttons, text='View run logs', command=lambda: self.open_folder(ROOT / 'logs')).pack(side='left', padx=8)
        ttk.Separator(frame).pack(fill='x', pady=14)
        ttk.Label(frame, text='First time: teach the agent', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='Select a store, open its priced menu, and teach each page you want checked.\nThen test an automatic run before enabling a schedule.').pack(anchor='w')
        self.tree = ttk.Treeview(frame, columns=('group', 'address', 'ready'), show='headings', height=5)
        for key, label, width in [('group', 'Group', 95), ('address', 'Store address', 490), ('ready', 'Autorun setup', 180)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width)
        self.tree.pack(fill='x', pady=8)
        actions = ttk.Frame(frame)
        actions.pack(fill='x')
        self.job_buttons = []
        for text, action in [('Teach selected store', self.teach), ('Run automatically now', lambda: self.start_job('run')),
                             ('Collect with browser help', lambda: self.start_job('guided'))]:
            button = ttk.Button(actions, text=text, command=action)
            button.pack(side='left', padx=(0, 8))
            self.job_buttons.append(button)
        schedule = ttk.LabelFrame(frame, text='Daily autorun', padding=10)
        schedule.pack(fill='x', pady=12)
        ttk.Label(schedule, text='Run daily at (24-hour computer time):').pack(side='left')
        self.time = tk.StringVar(value='09:00')
        ttk.Entry(schedule, textvariable=self.time, width=7).pack(side='left', padx=8)
        ttk.Button(schedule, text='Enable / update', command=self.enable_schedule).pack(side='left', padx=4)
        ttk.Button(schedule, text='Disable', command=self.disable_schedule).pack(side='left', padx=4)
        self.schedule_status = ttk.Label(frame, text='Scheduling requires your computer awake and your user signed in.')
        self.schedule_status.pack(anchor='w')
        self.status = tk.StringVar(value='Ready. Start by teaching each store, or choose browser help.')
        ttk.Label(frame, textvariable=self.status, wraplength=800).pack(anchor='w', pady=10)
        self.log = tk.Text(frame, height=7, wrap='word', state='disabled', font=('Consolas', 10))
        self.log.pack(fill='both', expand=True)
        self.refresh()
        window.after(150, self.poll)

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        try:
            profiles = json.loads((ROOT / 'config/profiles.json').read_text())
            for store in read_all(ROOT):
                config = profiles.get(store.profile, {})
                ready = 'Needs teaching'
                if config.get('mode') == 'trained' and config.get('store_id') == store.store_id:
                    ready = f"{len(config.get('pages', []))} taught pages"
                    if config.get('last_validated_at'):
                        ready += ' · tested'
                self.tree.insert('', 'end', iid=store.store_id, values=(store.group, store.address, ready))
            file = ROOT / 'local_state/schedule.json'
            if file.exists():
                settings = json.loads(file.read_text())
                self.time.set(settings.get('time', '09:00'))
                self.schedule_status.config(text=(f"Schedule saved for {settings['time']} daily. Computer must be awake and signed in."
                                                 if settings.get('enabled') else 'Daily schedule is disabled.'))
        except Exception as exc:
            messagebox.showerror('Could not read stores', str(exc), parent=self.window)

    def open_folder(self, path):
        path.mkdir(exist_ok=True)
        if os.name == 'nt':
            os.startfile(path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', str(path)])
        else:
            subprocess.Popen(['xdg-open', str(path)])

    def teach(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo('Choose a store', 'Click a store in the list, then Teach selected store.', parent=self.window)
            return
        self.start_job('teach', selected[0])

    def start_job(self, command, store_id=None):
        if self.process:
            return
        try:
            if command == 'run':
                missing = automatic_missing()
                if missing:
                    messagebox.showinfo('First-time setup needed', '\n'.join(missing), parent=self.window)
                    return
            interpreter = Path(sys.executable)
            if os.name == 'nt' and interpreter.name.lower() == 'pythonw.exe':
                interpreter = interpreter.with_name('python.exe')
            args = [str(interpreter), '-u', '-X', 'utf8', '-m', 'dunkin_compare.agent', command]
            if store_id:
                args += ['--store-id', store_id]
            kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
            self.process = subprocess.Popen(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            text=True, encoding='utf-8', errors='replace', **kwargs)
            self.status.set('Working. Use the browser panel if a browser opens; progress appears below.')
            for button in self.job_buttons:
                button.config(state='disabled')
            def monitor(process):
                for line in process.stdout:
                    self.events.put(('line', line))
                self.events.put(('done', process.wait()))
            threading.Thread(target=monitor, args=(self.process,), daemon=True).start()
        except Exception as exc:
            messagebox.showerror('Could not start', str(exc), parent=self.window)

    def poll(self):
        while not self.events.empty():
            kind, value = self.events.get()
            if kind == 'line':
                self.log.config(state='normal')
                self.log.insert('end', value)
                self.log.see('end')
                self.log.config(state='disabled')
            else:
                self.process = None
                for button in self.job_buttons:
                    button.config(state='normal')
                self.status.set('Finished. Open Excel reports, or continue setup.' if value == 0 else
                                'Needs attention. Read the messages below and check the report’s Store Status sheet.')
                self.refresh()
        self.window.after(150, self.poll)

    def enable_schedule(self):
        try:
            configure_schedule(self.time.get())
            self.refresh()
            messagebox.showinfo('Daily autorun enabled', 'The agent will check taught pages daily while this computer is awake and you are signed in. Reports and logs are saved locally.', parent=self.window)
        except Exception as exc:
            messagebox.showerror('Schedule needs setup', str(exc), parent=self.window)

    def disable_schedule(self):
        try:
            configure_schedule(self.time.get(), remove=True)
            self.refresh()
        except Exception as exc:
            messagebox.showerror('Could not disable schedule', str(exc), parent=self.window)

    def edit_stores(self, group):
        if self.process:
            messagebox.showinfo('Collection is running', 'Finish collection before editing stores.', parent=self.window)
            return
        dialog = tk.Toplevel(self.window)
        dialog.title('Our stores' if group == 'parent' else 'Competitor stores')
        dialog.geometry('680x440')
        dialog.transient(self.window)
        dialog.grab_set()
        stores = [s for s in read_all(ROOT) if s.group == group]
        tree = ttk.Treeview(dialog, columns=('address',), show='headings', height=7)
        tree.heading('address', text='Store address')
        tree.column('address', width=640)
        tree.pack(fill='x', padx=12, pady=12)
        address, market, channel = tk.StringVar(), tk.StringVar(value='northern_va'), tk.StringVar(value='pickup')
        def list_stores():
            tree.delete(*tree.get_children())
            for store in stores:
                tree.insert('', 'end', iid=store.store_id, values=(store.address,))
        def selected(event=None):
            if tree.selection():
                store = next(s for s in stores if s.store_id == tree.selection()[0])
                address.set(store.address);market.set(store.market);channel.set(store.channel)
        tree.bind('<<TreeviewSelect>>', selected)
        for label, variable in [('Full address', address), ('Comparison area (same for stores you want compared)', market)]:
            ttk.Label(dialog, text=label).pack(anchor='w', padx=12)
            ttk.Entry(dialog, textvariable=variable).pack(fill='x', padx=12)
        ttk.Label(dialog, text='Pricing channel').pack(anchor='w', padx=12)
        ttk.Combobox(dialog, textvariable=channel, values=['pickup', 'delivery', 'in_store'], state='readonly').pack(anchor='w', padx=12)
        row = ttk.Frame(dialog, padding=12)
        row.pack(fill='x')
        def save(add=False):
            if not address.get().strip() or not market.get().strip():
                messagebox.showerror('Missing information', 'Enter an address and comparison area.', parent=dialog)
                return
            if add:
                stores.append(Store(group, group+'_'+uuid.uuid4().hex[:10], 'Dunkin', address.get().strip(),
                                    market.get().strip(), channel.get(), '', 'structured_menu'))
            elif tree.selection():
                index = next(i for i,s in enumerate(stores) if s.store_id == tree.selection()[0])
                store = stores[index]
                changed = store.address != address.get().strip() or store.channel != channel.get()
                stores[index] = replace(store, address=address.get().strip(), market=market.get().strip(),
                                        channel=channel.get(), profile='structured_menu' if changed else store.profile,
                                        menu_url='' if changed else store.menu_url)
            else:
                messagebox.showinfo('Choose a store', 'Choose an existing store or click Add as new store.', parent=dialog)
                return
            try:
                write_group(ROOT, group, stores)
                list_stores();self.refresh()
            except Exception as exc:
                messagebox.showerror('Could not save', str(exc), parent=dialog)
        def remove():
            if not tree.selection():
                return
            if messagebox.askyesno('Remove store?', 'Remove this address from the collection list?', parent=dialog):
                stores[:] = [s for s in stores if s.store_id != tree.selection()[0]]
                write_group(ROOT, group, stores);list_stores();self.refresh()
        ttk.Button(row, text='Add as new store', command=lambda: save(True)).pack(side='left', padx=3)
        ttk.Button(row, text='Update selected', command=save).pack(side='left', padx=3)
        ttk.Button(row, text='Remove selected', command=remove).pack(side='left', padx=3)
        ttk.Button(row, text='Done', command=dialog.destroy).pack(side='right')
        list_stores()

    def close(self):
        if self.process:
            messagebox.showinfo('Collection is running', 'Finish or close the collection browser and wait for this job to finish before closing the app.', parent=self.window)
            return
        self.window.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
