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
        ttk.Label(frame, text='Automatic collection', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='AI discovers page controls without teaching. Choose free local AI in AI settings.\nManual browser help and taught layouts remain optional. Test Run now before scheduling.').pack(anchor='w')
        self.tree = ttk.Treeview(frame, columns=('group', 'address', 'ready'), show='headings', height=5)
        for key, label, width in [('group', 'Group', 95), ('address', 'Store address', 490), ('ready', 'Autorun setup', 180)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width)
        self.tree.pack(fill='x', pady=8)
        actions = ttk.Frame(frame)
        actions.pack(fill='x')
        self.job_buttons = []
        for text, action in [('AI settings', self.ai_settings), ('Optional: teach a layout', self.teach), ('Run automatically now', lambda: self.start_job('run')),
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
        self.status = tk.StringVar(value='Ready. Open AI settings for automatic page discovery, or use browser help.')
        ttk.Label(frame, textvariable=self.status, wraplength=800).pack(anchor='w', pady=10)
        self.log = tk.Text(frame, height=7, wrap='word', state='disabled', font=('Consolas', 10))
        self.log.pack(fill='both', expand=True)
        self.refresh()
        window.after(150, self.poll)

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        try:
            profiles = json.loads((ROOT / 'config/profiles.json').read_text())
            from .ai_runner import settings
            ai = settings(ROOT)
            stores=read_all(ROOT)
            from .ai_runner import store_signature
            for store in stores:
                config = profiles.get(store.profile, {})
                ready = 'Choose AI mode'
                if ai.get('enabled'):
                    ready = 'AI discovers page'
                    if ai.get('last_validated_at') and ai.get('last_validated_stores')==store_signature(stores):
                        ready += ' · tested'
                elif config.get('mode') == 'trained' and config.get('store_id') == store.store_id:
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
                    from .ai_runner import settings
                    if not settings(ROOT).get('enabled'):
                        messagebox.showinfo('Enable page discovery',
                                            'Open AI settings and choose free local AI or the optional paid API. No teaching is required in AI mode.',parent=self.window)
                        self.ai_settings()
                        return
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
            missing=automatic_missing(require_test=True)
            if missing:
                raise ValueError('\n'.join(missing))
            from .ai_runner import settings
            if settings(ROOT).get('enabled') and settings(ROOT).get('provider','openai')=='openai' and not messagebox.askyesno(
                    'Enable daily AI usage?',
                    'Daily runs send ordering-page screenshots/text to OpenAI and use your API billing account. '
                    'The AI-step limit is not a dollar-spending limit. Enable daily AI runs?',parent=self.window):
                return
            configure_schedule(self.time.get())
            self.refresh()
            messagebox.showinfo('Daily autorun enabled', 'The agent will collect prices daily while this computer is awake and you are signed in. Keep Ollama running if using local AI. Reports and logs are saved locally.', parent=self.window)
        except Exception as exc:
            messagebox.showerror('Schedule needs setup', str(exc), parent=self.window)

    def disable_schedule(self):
        try:
            configure_schedule(self.time.get(), remove=True)
            self.refresh()
        except Exception as exc:
            messagebox.showerror('Could not disable schedule', str(exc), parent=self.window)

    def ai_settings(self):
        if self.process:
            return
        from .ai_runner import settings
        from .ai_credentials import get_key, save_key
        from .training import atomic_json
        config=settings(ROOT)
        dialog=tk.Toplevel(self.window)
        dialog.title('AI page discovery settings')
        dialog.geometry('650x560')
        dialog.transient(self.window)
        dialog.grab_set()
        frame=ttk.Frame(dialog,padding=16)
        frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='No teaching: AI reads the page and its options',font=('Segoe UI',13,'bold')).pack(anchor='w')
        def api_key_page():
            import webbrowser
            webbrowser.open('https://platform.openai.com/api-keys')
        choice=tk.StringVar(value='Paid OpenAI API' if config.get('provider','openai' if config.get('enabled') else 'ollama')=='openai' else 'Free local (Ollama)')
        ttk.Label(frame,text='AI provider').pack(anchor='w',pady=(10,0))
        chooser=ttk.Combobox(frame,textvariable=choice,state='readonly',values=['Free local (Ollama)','Paid OpenAI API'],width=32)
        chooser.pack(anchor='w')
        explanation=tk.StringVar()
        ttk.Label(frame,textvariable=explanation,wraplength=600).pack(anchor='w',pady=8)
        local_frame=ttk.Frame(frame)
        local_frame.pack(fill='x')
        model=tk.StringVar(value=config.get('local_model','gemma3:4b'))
        ttk.Label(local_frame,text='Local vision model').pack(anchor='w')
        ttk.Entry(local_frame,textvariable=model,width=30).pack(anchor='w')
        def download_ollama():
            import webbrowser
            webbrowser.open('https://ollama.com/download/mac' if sys.platform=='darwin' else 'https://ollama.com/download')
        ttk.Button(local_frame,text='Download Ollama (free)',command=download_ollama).pack(anchor='w',pady=4)
        if sys.platform=='darwin':
            ttk.Button(local_frame,text='Prepare free model',command=lambda:subprocess.Popen(['open',str(ROOT/'Prepare Free AI Mac.command')])).pack(anchor='w')
        paid_frame=ttk.Frame(frame)
        enabled=tk.BooleanVar(value=config.get('enabled',False))
        shown=tk.BooleanVar(value=config.get('show_browser',True))
        steps=tk.StringVar(value=str(config.get('max_steps',60)))
        key=tk.StringVar()
        ttk.Checkbutton(frame,text='Use AI discovery for Run now and scheduled runs',variable=enabled).pack(anchor='w')
        ttk.Button(paid_frame,text='Open API key page',command=api_key_page).pack(anchor='w')
        ttk.Label(paid_frame,text='API key (saved in Mac Keychain or Windows Credential Manager)').pack(anchor='w')
        ttk.Entry(paid_frame,textvariable=key,show='•',width=65).pack(fill='x')
        ttk.Label(paid_frame,text='Leave blank to keep an existing saved key. Never paste it into chat.').pack(anchor='w')
        def provider_changed(event=None):
            local_frame.pack_forget();paid_frame.pack_forget()
            if choice.get()=='Free local (Ollama)':
                local_frame.pack(fill='x',after=chooser)
                explanation.set('No API key or usage charges. Screenshots stay in local inference on this computer. Install/open Ollama and prepare the model once. 16 GB+ memory is recommended; small local models may struggle with complex menus.')
            else:
                paid_frame.pack(fill='x',after=chooser)
                explanation.set('Separate OpenAI API billing. ChatGPT subscriptions do not include API usage. Screenshots and page text are sent to OpenAI. The call limit is not a dollar cap.')
        chooser.bind('<<ComboboxSelected>>',provider_changed)
        provider_changed()
        line=ttk.Frame(frame)
        line.pack(fill='x',pady=10)
        ttk.Label(line,text='Maximum AI steps per store (1–200):').pack(side='left')
        ttk.Entry(line,textvariable=steps,width=6).pack(side='left',padx=8)
        ttk.Checkbutton(frame,text='Show the browser while AI works',variable=shown).pack(anchor='w')
        ttk.Label(frame,text='Prices require observed store, channel, item, size and exact price evidence.').pack(anchor='w',pady=8)
        def save():
            try:
                limit=int(steps.get())
                if not 1<=limit<=200:
                    raise ValueError('Choose 1–200 calls per store.')
                provider='ollama' if choice.get()=='Free local (Ollama)' else 'openai'
                schedule_file=ROOT/'local_state/schedule.json'
                if enabled.get() and provider=='openai' and (not config.get('enabled') or config.get('provider','openai')!='openai') and schedule_file.exists() and json.loads(schedule_file.read_text()).get('enabled'):
                    if not messagebox.askyesno('Use AI in the existing daily schedule?',
                                               'Your daily schedule will also send page screenshots/text to OpenAI and use your API billing account. Continue?',parent=dialog):
                        return
                if provider=='ollama':
                    import re
                    if not re.fullmatch(r'[A-Za-z0-9._/:+\-]{1,100}',model.get().strip()) or 'cloud' in model.get().lower():
                        raise ValueError('Choose a local vision model, not a cloud model.')
                if provider=='openai' and key.get().strip():
                    save_key(key.get())
                if enabled.get() and provider=='openai' and not get_key():
                    raise ValueError('An API key is required to enable AI discovery.')
                atomic_json(ROOT/'local_state/ai_settings.json',{
                    'enabled':enabled.get(),'max_steps':limit,'show_browser':shown.get(),
                    'provider':provider,'local_model':model.get().strip()})
                key.set('')
                dialog.destroy()
                self.refresh()
                self.status.set('AI settings saved. Click Run automatically now to test. No teaching is required in AI mode.')
            except Exception as exc:
                messagebox.showerror('Could not save AI settings',str(exc),parent=dialog)
        ttk.Button(frame,text='Save settings',command=save).pack(anchor='e')

    def edit_stores(self, group):
        if self.process:
            messagebox.showinfo('Collection is running', 'Finish collection before editing stores.', parent=self.window)
            return
        dialog = tk.Toplevel(self.window)
        dialog.title('Our stores' if group == 'parent' else 'Competitor stores')
        dialog.geometry('680x510')
        dialog.transient(self.window)
        dialog.grab_set()
        stores = [s for s in read_all(ROOT) if s.group == group]
        tree = ttk.Treeview(dialog, columns=('address',), show='headings', height=7)
        tree.heading('address', text='Store address')
        tree.column('address', width=640)
        tree.pack(fill='x', padx=12, pady=12)
        address, market, channel = tk.StringVar(), tk.StringVar(value='northern_va'), tk.StringVar(value='pickup')
        menu_url=tk.StringVar()
        def list_stores():
            tree.delete(*tree.get_children())
            for store in stores:
                tree.insert('', 'end', iid=store.store_id, values=(store.address,))
        def selected(event=None):
            if tree.selection():
                store = next(s for s in stores if s.store_id == tree.selection()[0])
                address.set(store.address);market.set(store.market);channel.set(store.channel);menu_url.set(store.menu_url)
        tree.bind('<<TreeviewSelect>>', selected)
        for label, variable in [('Full address', address), ('Comparison area (same for stores you want compared)', market)]:
            ttk.Label(dialog, text=label).pack(anchor='w', padx=12)
            ttk.Entry(dialog, textvariable=variable).pack(fill='x', padx=12)
        ttk.Label(dialog, text='Pricing channel').pack(anchor='w', padx=12)
        ttk.Combobox(dialog, textvariable=channel, values=['pickup', 'delivery', 'in_store'], state='readonly').pack(anchor='w', padx=12)
        ttk.Label(dialog,text='Ordering page URL (optional; leave blank to start on Dunkin)').pack(anchor='w',padx=12,pady=(8,0))
        ttk.Entry(dialog,textvariable=menu_url).pack(fill='x',padx=12)
        row = ttk.Frame(dialog, padding=12)
        row.pack(fill='x')
        def save(add=False):
            if not address.get().strip() or not market.get().strip():
                messagebox.showerror('Missing information', 'Enter an address and comparison area.', parent=dialog)
                return
            if add:
                stores.append(Store(group, group+'_'+uuid.uuid4().hex[:10], 'Dunkin', address.get().strip(),
                                    market.get().strip(), channel.get(), menu_url.get().strip(), 'structured_menu'))
            elif tree.selection():
                index = next(i for i,s in enumerate(stores) if s.store_id == tree.selection()[0])
                store = stores[index]
                changed = store.address != address.get().strip() or store.channel != channel.get() or store.menu_url!=menu_url.get().strip()
                stores[index] = replace(store, address=address.get().strip(), market=market.get().strip(),
                                        channel=channel.get(), profile='structured_menu' if changed else store.profile,
                                        menu_url=menu_url.get().strip())
            else:
                messagebox.showinfo('Choose a store', 'Choose an existing store or click Add as new store.', parent=dialog)
                return
            try:
                write_group(ROOT, group, stores)
                from .ai_runner import settings
                from .training import atomic_json
                ai=settings(ROOT)
                if ai:
                    ai.pop('last_validated_at',None)
                    atomic_json(ROOT/'local_state/ai_settings.json',ai)
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
