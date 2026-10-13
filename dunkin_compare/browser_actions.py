"""Evidence-based browser actions shared by adaptive menu collectors."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

from .core import make_item, normalized


def address_matches(observed, expected):
    replacements={'boulevard':'blvd','drive':'dr','street':'st','road':'rd','avenue':'ave',
                  'lane':'ln','highway':'hwy','court':'ct','virginia':'va'}
    def words(text):
        return [replacements.get(w,w) for w in normalized(text).split()]
    target=words(expected)
    actual=words(observed)
    # Require the numbered street, city and state; a ZIP on the page may be additional.
    return bool(target and any(w.isdigit() for w in target)) and all(w in actual for w in target)


class PageController:
    def __init__(self, page, store):
        self.page,self.store=page,store
        self.allowed_hosts={'dunkindonuts.com','www.dunkindonuts.com','locations.dunkindonuts.com'}
        initial=urlsplit(store.menu_url or page.url).hostname
        if initial:
            self.allowed_hosts.add(initial)
        self.script=Path(__file__).with_name('page_snapshot.js').read_text()

    def snapshot(self):
        host=urlsplit(self.page.url).hostname
        if host not in self.allowed_hosts:
            raise ValueError('Ordering website changed to an unapproved destination. Set its menu URL in store settings.')
        return self.page.evaluate(self.script)

    def resolve(self, snapshot, identifier):
        entry=next((e for e in snapshot['elements'] if e['id']==identifier),None)
        if not entry or not re.fullmatch(r'e\d+',str(identifier)):
            raise ValueError('Agent cited an element that was not observed')
        node=self.page.locator(f'[data-dpc-ai="{identifier}"]')
        if node.count()!=1 or not node.is_visible():
            raise ValueError('Page changed; cited element is no longer visible')
        current=node.evaluate("el => el.tagName==='SELECT' ? Array.from(el.selectedOptions).map(o=>o.textContent.trim()).join(' ') : (el.innerText||el.textContent||'').trim().slice(0,250)")
        if current!=entry['text']:
            raise ValueError('Page changed since inspection; refresh before acting')
        return entry,node

    def act(self, snapshot, decision):
        action=decision.get('action')
        if action=='scroll':
            direction=decision.get('direction')
            if direction not in ('up','down'):
                raise ValueError('Unknown scroll direction')
            self.page.mouse.wheel(0,600 if direction=='down' else -600)
            self.page.wait_for_timeout(500)
            return
        if action not in ('click','fill','select','back'):
            raise ValueError('Unsupported browser action')
        if action=='back':
            self.page.go_back(wait_until='domcontentloaded',timeout=30000)
            return
        entry,node=self.resolve(snapshot,decision.get('element_id'))
        if action=='fill':
            if entry['tag']!='input' or entry['type'] not in ('text','search') or not re.search(
                    r'address|location|store|city|zip|search',entry['label'],re.I):
                raise ValueError('Only a store-address search field may be filled')
            if decision.get('text')!=self.store.address:
                raise ValueError('Agent can only enter the configured store address')
            node.fill(self.store.address)
            return
        if action=='select':
            if entry['tag']!='select' or not any(o['value']==decision.get('value') and not o['disabled'] for o in entry['options']):
                raise ValueError('Agent selected an option not observed on the page')
            node.select_option(decision['value'])
        else:
            label=(entry['label']+' '+entry['text']).lower()
            source=urlsplit(self.page.url).hostname or ''
            official_order=(source=='dunkindonuts.com' or source.endswith('.dunkindonuts.com')) and bool(re.search(r'order|menu',label))
            if not entry['control'] or re.search(r'checkout|place\s+order|confirm\s+order|pay(?:ment)?\b|purchase|buy\b|add\s+to\s+(?:cart|bag|order)|sign\s+in|log\s*in|create\s+account',label):
                raise ValueError('This control is outside menu research; no orders or logins are performed')
            if entry['href']:
                target=urlsplit(entry['href'])
                if target.scheme!='https' or target.username or target.password:
                    raise ValueError('Agent navigation must use public HTTPS links')
                if target.hostname not in self.allowed_hosts:
                    if not official_order:
                        raise ValueError('External navigation is not an official Dunkin ordering link')
                    self.allowed_hosts.add(target.hostname)
            before=len(self.page.context.pages)
            node.click(timeout=15000)
            self.page.wait_for_timeout(800)
            if len(self.page.context.pages)>before:
                self.page=self.page.context.pages[-1]
                self.page.wait_for_load_state('domcontentloaded',timeout=30000)
            destination=urlsplit(self.page.url)
            if destination.hostname not in self.allowed_hosts:
                if not official_order or destination.scheme!='https' or destination.username or destination.password:
                    raise ValueError('Navigation left the approved menu websites')
                self.allowed_hosts.add(destination.hostname)
        self.page.wait_for_timeout(500)

    def extract(self, snapshot, decision):
        address,_=self.resolve(snapshot,decision.get('store_address_id'))
        if not address['store_context'] or not address_matches(address['text'],self.store.address):
            raise ValueError('Price source does not verify the configured selected-store address')
        channel,_=self.resolve(snapshot,decision.get('channel_id'))
        text=normalized(channel['text'] or channel['label'])
        expected=self.store.channel
        if expected=='pickup':
            matches='pickup' in text.replace(' ','')
        elif expected=='delivery':
            matches='delivery' in text
        else:
            raise ValueError('Web agent supports pickup or delivery menus; in-store prices cannot be inferred')
        if not matches or not (channel['selected'] or re.search(r'pickup (?:at|from)|pick up (?:at|from)|delivery from',text)):
            raise ValueError('The active pricing channel could not be verified')
        rows=decision.get('rows',[])
        if not isinstance(rows,list) or not rows or len(rows)>100:
            raise ValueError('Agent must cite between 1 and 100 observed item rows')
        items=[]
        for row in rows:
            observed={}
            nodes={}
            for field in ('name','price','category','variant'):
                observed[field],nodes[field]=self.resolve(snapshot,row.get(field+'_id'))
            if not observed['variant']['text']:
                raise ValueError('No observed size/variant; price not recorded')
            if (observed['variant']['option_control'] or observed['variant']['interactive_parent']) and not observed['variant']['selected'] and observed['variant']['tag']!='select':
                raise ValueError('Variant is an available option, not the selected size')
            connected=nodes['name'].evaluate("""(name, priceId) => {
              const price=document.querySelector('[data-dpc-ai="'+priceId+'"]');
              const container='article,[role="dialog"],dialog,[role="button"]';
              const nameCard=name.closest(container),priceCard=price?.closest(container);
              if(nameCard||priceCard) return !!nameCard&&nameCard===priceCard;
              let parent=name.parentElement;
              while(parent&&!parent.contains(price)) parent=parent.parentElement;
              return !!parent&&!['HTML','BODY','MAIN'].includes(parent.tagName)&&parent.innerText.length<2000&&
                parent.querySelectorAll('h1,h2,h3,h4').length<=1;
            }""",observed['price']['id'])
            if not connected:
                raise ValueError('Name and price do not belong to the same item card/dialog')
            if observed['category']['control'] and not observed['category']['selected']:
                raise ValueError('Category is an available navigation option, not the active category')
            if not observed['variant']['selected'] and observed['variant']['tag']!='select':
                same_card=nodes['name'].evaluate("""(name, ids) => {
                  const price=document.querySelector('[data-dpc-ai="'+ids.price+'"]');
                  const variant=document.querySelector('[data-dpc-ai="'+ids.variant+'"]');
                  let parent=name.parentElement;
                  while(parent&&!parent.contains(price)) parent=parent.parentElement;
                  return !!parent&&parent.contains(variant);
                }""",{'price':observed['price']['id'],'variant':observed['variant']['id']})
                if not same_card:
                    raise ValueError('Size text is not associated with this item or an active size selection')
            if '$' not in observed['price']['text']:
                raise ValueError('Price lacks an observed dollar symbol; currency is ambiguous')
            items.append(make_item(category=observed['category']['text'],name=observed['name']['text'],
                                   variant=observed['variant']['text'],price=observed['price']['text'],currency='USD'))
        return items
