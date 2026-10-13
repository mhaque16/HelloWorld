"""Adaptive collection with bounded AI calls and source-grounded price evidence."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .browser_actions import PageController
from .core import deduplicate
from .desktop_data import read_all
from .report import write_report


def settings(root):
    path=root/'local_state/ai_settings.json'
    return json.loads(path.read_text()) if path.exists() else {}


def store_signature(stores):
    import hashlib
    return hashlib.sha256(json.dumps([s.__dict__ for s in stores],sort_keys=True).encode()).hexdigest()


def run_store(page,store,planner,max_steps,trace=None):
    controller=PageController(page,store)
    items,sources,history=[],[],[]
    last_error=''
    rejects=0
    message='AI step limit reached before menu traversal completed'
    status='partial'
    for step in range(max_steps):
        try:
            snapshot=controller.snapshot()
            image=controller.page.screenshot(type='png')
            decision=planner.decide(store,snapshot,image,history,last_error)
            action=decision.get('action')
            entry={'step':step+1,'action':action,'reason':str(decision.get('reason',''))[:500]}
            if action=='done':
                if not items:
                    raise ValueError('Agent reached completion without any verified menu prices')
                status='ai_collected'
                message='AI reported completion; full-menu coverage is not independently verified. '+entry['reason']
                history.append(entry)
                break
            if action=='blocked':
                message='Agent could not continue: '+entry['reason']
                history.append(entry)
                break
            if action=='extract':
                observed=controller.extract(snapshot,decision)
                items=deduplicate(items+observed)
                if controller.page.url not in sources:
                    sources.append(controller.page.url)
                entry['items']=[{**item.__dict__,'price':str(item.price)} for item in observed]
                print(f'{store.store_id}: verified {len(items)} item/size prices',flush=True)
            else:
                controller.act(snapshot,decision)
            last_error=''
            rejects=0
            history.append(entry)
        except ValueError as exc:
            last_error=str(exc)
            rejects+=1
            history.append({'step':step+1,'rejected':last_error})
            if rejects>=3:
                message='Repeated evidence/navigation check failures: '+last_error
                break
        except Exception as exc:
            # Preserve already validated rows, but never label this store complete.
            message=f'Collection stopped: {type(exc).__name__}: {exc}'
            break
        finally:
            if trace:
                trace.parent.mkdir(parents=True,exist_ok=True)
                trace.write_text(json.dumps({'store_id':store.store_id,'steps':history},indent=2),encoding='utf-8')
    if not items:
        status='failed'
    return items,'\n'.join(sources),status,message


def run(root):
    from playwright.sync_api import sync_playwright
    from .ai_credentials import get_key
    from .ai_planner import VisionPlanner
    from .interactive import launch_visible
    config=settings(root)
    provider=config.get('provider','openai')
    if provider=='ollama':
        from .local_planner import check_local,LocalVisionPlanner
        model=config.get('local_model','gemma3:4b')
        check_local(model)
        planner_factory=lambda:LocalVisionPlanner(model)
    elif provider=='openai':
        key=get_key()
        if not key:
            raise ValueError('Add your API key using the AI settings button first. No key is stored in the download.')
        planner_factory=lambda:VisionPlanner(key)
    else:
        raise ValueError('Choose local Ollama or OpenAI in AI settings.')
    max_steps=config.get('max_steps',60)
    if type(max_steps) is not int or not 1<=max_steps<=200:
        raise ValueError('AI step limit must be between 1 and 200 per store')
    stores=read_all(root)
    collected,statuses=[],[]
    stamp=datetime.now(ZoneInfo('America/New_York')).strftime('%Y%m%d_%H%M%S_%f')
    with sync_playwright() as p:
        browser=launch_visible(p,'auto',headless=not config.get('show_browser',True))
        try:
            for index,store in enumerate(stores):
                context=browser.new_context(viewport={'width':1280,'height':900})
                planner=planner_factory()
                try:
                    page=context.new_page()
                    target=store.menu_url or 'https://www.dunkindonuts.com/en'
                    from .collect import check_robots
                    check_robots(target)
                    response=page.goto(target,wait_until='domcontentloaded',timeout=45000)
                    if response is None or response.status>=400:
                        raise ValueError('Menu page is unavailable; no access restrictions are bypassed')
                    items,source,status,message=run_store(page,store,planner,max_steps,
                                                         root/'local_state/ai_runs'/f'{stamp}_{index}.json')
                    if items:
                        collected.append((store,items,source))
                except Exception as exc:
                    items,source,status,message=[], '', 'failed', str(exc)
                finally:
                    context.close()
                statuses.append({'group':store.group,'store_id':store.store_id,'address':store.address,
                                 'status':status,'item_count':len(items),
                                 'message':message+f' Provider: {provider}; inference calls: {planner.calls}; input tokens: {planner.input_tokens}; output tokens: {planner.output_tokens}.'})
                print(f'{store.store_id}: {status}. {message}',flush=True)
        finally:
            browser.close()
    now=datetime.now(ZoneInfo('America/New_York'))
    output=root/'reports'/f'AI_menu_prices_{stamp}.xlsx'
    write_report(output,collected,statuses,now,capture_method=f'{provider} AI navigation with DOM-evidenced prices (coverage unverified)')
    print(f'Saved {output}',flush=True)
    result=0 if statuses and all(s['status']=='ai_collected' for s in statuses) else 1
    if result==0:
        from .training import atomic_json
        config['last_validated_at']=now.isoformat()
        config['last_validated_stores']=store_signature(stores)
        atomic_json(root/'local_state/ai_settings.json',config)
    return result
