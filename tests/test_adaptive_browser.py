import shutil
import unittest
from dataclasses import replace
from pathlib import Path

from dunkin_compare.ai_runner import run_store
from dunkin_compare.browser_actions import PageController, address_matches
from tests.support import PARENT

ROOT=Path(__file__).resolve().parent.parent


class AdaptiveBrowserTests(unittest.TestCase):
    def test_address_abbreviations_without_accepting_other_store(self):
        self.assertTrue(address_matches('13801 Heathcote Blvd, Gainesville, VA 20155',PARENT.address))
        self.assertFalse(address_matches('13802 Heathcote Blvd, Gainesville, VA',PARENT.address))
        self.assertFalse(address_matches('13801 Heathcote Blvd, Ashburn, VA',PARENT.address))

    def test_search_categories_sizes_and_evidence_based_extraction(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            executable=p.chromium.executable_path
            if not Path(executable).exists():
                executable=shutil.which('chromium') or shutil.which('chromium-browser')
            if not executable:
                self.skipTest('Chromium not installed')
            browser=p.chromium.launch(headless=True,executable_path=executable)
            try:
                context=browser.new_context()
                fixture=(ROOT/'tests/fixtures/adaptive_menu.html').read_text()
                context.route('https://menu.example.test/**',lambda route:route.fulfill(body=fixture,content_type='text/html'))
                page=context.new_page()
                page.goto('https://menu.example.test/menu')
                store=replace(PARENT,menu_url=page.url)
                def find(snapshot,text,tag=None):
                    choices=[e for e in snapshot['elements'] if (e['text']==text or e['label']==text) and (not tag or e['tag']==tag)]
                    self.assertTrue(choices, f'Missing observed element: {text}')
                    return choices[0]['id']
                def extract(snapshot,category,size):
                    return {'action':'extract','store_address_id':find(snapshot,'13801 Heathcote Blvd, Gainesville, VA'),
                            'channel_id':find(snapshot,'Pickup','button'),
                            'rows':[{'name_id':find(snapshot,'Hot Coffee' if category=='Coffee' else 'Glazed Donut','h2'),
                                     'price_id':find(snapshot,'$2.49' if size=='Small' else '$3.29' if size=='Medium' else '$1.79','p'),
                                     'category_id':find(snapshot,category,'button'),'variant_id':find(snapshot,size,'select')}]}
                plan=[lambda s:{'action':'click','element_id':find(s,'Find a store')},
                      lambda s:{'action':'fill','element_id':find(s,'Search address'),'text':store.address},
                      lambda s:{'action':'click','element_id':find(s,'Search','button')},
                      lambda s:{'action':'click','element_id':find(s,'Hot Coffee\nFrom $2.49','div')},
                      lambda s:extract(s,'Coffee','Small'),
                      lambda s:{'action':'select','element_id':find(s,'Small','select'),'value':'medium'},
                      lambda s:extract(s,'Coffee','Medium'),
                      lambda s:{'action':'click','element_id':find(s,'Close options')},
                      lambda s:{'action':'click','element_id':find(s,'Donuts','button')},
                      lambda s:{'action':'click','element_id':find(s,'Glazed Donut\nFrom $2.49','div')},
                      lambda s:extract(s,'Donuts','Single'),
                      lambda s:{'action':'done','reason':'Synthetic categories and sizes traversed'}]
                class Planner:
                    index=0
                    def decide(self,store,snapshot,image,history,last_error):
                        if last_error:
                            raise AssertionError(last_error)
                        assert image.startswith(b'\x89PNG')
                        action=plan[self.index](snapshot)
                        self.index+=1
                        return action
                items,source,status,message=run_store(page,store,Planner(),20)
                self.assertEqual(status,'ai_collected',message)
                self.assertEqual([(i.name,i.variant,str(i.price)) for i in items],
                                 [('Hot Coffee','Small','2.49'),('Hot Coffee','Medium','3.29'),('Glazed Donut','Single','1.79')])
                controller=PageController(page,store)
                snap=controller.snapshot()
                with self.assertRaisesRegex(ValueError,'no orders'):
                    controller.act(snap,{'action':'click','element_id':find(snap,'Add to cart')})
                self.assertFalse(page.evaluate('!!window.orderWasChanged'))
                bad=extract(snap,'Donuts','Single')
                bad['rows'][0]['price_id']='invented_price'
                with self.assertRaisesRegex(ValueError,'not observed'):
                    controller.extract(snap,bad)
                with self.assertRaisesRegex(ValueError,'not observed'):
                    controller.act(snap,{'action':'click','element_id':'e999999'})
            finally:
                browser.close()
