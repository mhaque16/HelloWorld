(() => {
  // Only a user-initiated capture reads menu text. No page scripts or endpoints are guessed.
  if (window.top !== window) return;
  async function install() {
    if (!document.body || document.getElementById('dpc-collector')) return;
    if (typeof window.__dpcState !== 'function') return;
    const state = await window.__dpcState();
    const host = document.createElement('div');
    host.id = 'dpc-collector';
    host.style.cssText = 'position:fixed;top:12px;right:12px;z-index:2147483647;width:460px;max-width:95vw;';
    const ui = host.attachShadow({mode: 'open'});
    ui.innerHTML = `
      <style>
        :host { all: initial; color-scheme: light; }
        * { box-sizing: border-box; }
        .panel { font:14px/1.4 Arial,sans-serif;color:#18212d;background:#fff;border:2px solid #e56618;
          border-radius:10px;box-shadow:0 6px 30px #0005;max-height:90vh;overflow:auto; }
        header { background:#17365d;color:white;padding:12px;display:flex;justify-content:space-between;align-items:center; }
        h2 {font-size:16px;margin:0;} .body{padding:12px;} p{margin:8px 0;} .muted{color:#46566a;font-size:12px;}
        button {font:inherit;background:#edf2f7;color:#17365d;border:1px solid #bcc9d7;border-radius:4px;padding:6px 9px;cursor:pointer;}
        button.primary {background:#17365d;color:white;} button:disabled{opacity:.5;cursor:wait;}
        input[type=text] {font:inherit;width:100%;padding:6px;border:1px solid #bcc9d7;border-radius:4px;color:#18212d;background:white;}
        input[type=checkbox]{margin-right:6px;} label {display:block;margin-top:8px;}
        .field {display:grid;grid-template-columns:1fr auto;gap:6px;align-items:end;}
        .actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px;}
        #message {white-space:pre-wrap;padding:8px;background:#f1f5f9;border-radius:4px;font-size:13px;}
        .error{color:#9c1c24;} #preview {overflow:auto;max-height:230px;margin-top:10px;}
        table{border-collapse:collapse;font-size:12px;min-width:700px;} th,td{border:1px solid #d5dde5;padding:4px;text-align:left;}
        td input[type=text]{font-size:12px;min-width:85px;} #count{font-weight:bold;} .hidden{display:none;}
      </style>
      <section class="panel">
        <header><h2>Menu Price Collector</h2><button id="minimize" title="Hide panel while navigating">Hide</button></header>
        <div class="body" id="body">
          <p><strong id="store"></strong><br><span id="address"></span><br><strong id="channel"></strong></p>
          <p class="muted">1. Use the site's store picker. Open its priced ordering menu, not the national menu.
            This tool never selects a store or changes an order for you.</p>
          <label><input id="verified" type="checkbox">I checked that the selected store address and pricing channel match those above.</label>
          <button id="confirm">Confirm store on this page</button>
          <div id="teaching" class="hidden">
            <p><strong>Teach autorun for this page</strong></p>
            <p class="muted">Pick the selected-store address below. Also pick the category and size from visible text,
            not just typed fields. Preview and review the menu cards before teaching. Repeat on each menu page you need.
            Autorun reads only taught pages and does not click through categories or size options.</p>
            <div class="field"><label>Selected address text<input id="location" type="text"></label><button data-pick="location">Pick address</button></div>
          </div>
          <p class="muted">2. Click Pick, then click the matching text on the menu. You can also type corrections.
            Navigate categories and open size options yourself.</p>
          <div class="field"><label>Category<input id="category" type="text" placeholder="e.g. Coffee"></label><button data-pick="category">Pick category</button></div>
          <div class="field"><label>Item name<input id="name" type="text"></label><button data-pick="name">Pick name</button></div>
          <div class="field"><label>Size / variant<input id="variant" type="text" placeholder="e.g. Small, Medium, Single"></label><button data-pick="variant">Pick size</button></div>
          <div class="field"><label>Displayed USD price<input id="price" type="text" placeholder="$2.49"></label><button data-pick="price">Pick price</button></div>
          <div class="actions"><button id="single">Preview this item</button><button id="similar">Preview similar cards</button><button id="cancelpick">Cancel pick</button></div>
          <p class="muted">Similar-card collection reads visible cards with the same structure as the picked name and price.
            Category/size can be shared from the fields above. Verify each row; it may miss items or choose the wrong container.</p>
          <div id="preview"></div>
          <div class="actions"><button id="selectall">Select all after review</button><button id="clear">Clear preview</button></div>
          <label><input id="reviewed" type="checkbox">I reviewed every selected row's item, price, category, and size.</label>
          <button id="save" class="primary">Save selected rows</button>
          <button id="train" class="primary hidden">Teach autorun this page</button>
          <p>Saved for this store: <span id="count">0</span></p>
          <div id="message" role="status">Select the store in the ordering website, then confirm it here.</div>
          <p class="muted">3. Repeat for every category and size you need. Only rows you save are exported.</p>
          <div class="actions"><button id="finish" class="primary">Finish store / next</button><button id="skip">Skip store</button></div>
        </div>
      </section>`;
    document.body.appendChild(host);
    const $ = id => ui.getElementById(id);
    $('store').textContent = `${state.group.toUpperCase()} · ${state.store_id}`;
    $('address').textContent = state.address;
    $('channel').textContent = `Channel: ${state.channel} · Currency: USD`;
    $('count').textContent = state.count;
    if(state.training) {
      $('teaching').classList.remove('hidden');$('train').classList.remove('hidden');
      $('finish').textContent='Finish teaching this store';
    }
    let picking = null;
    let refs = {};
    let preview = [];
    let confirmed = false;
    const highlight = document.createElement('div');
    highlight.style.cssText = 'display:none;position:fixed;pointer-events:none;z-index:2147483646;border:3px solid #e56618;background:#e5661820;';
    document.body.appendChild(highlight);
    function message(text, error = false) {
      $('message').textContent = text;
      $('message').className = error ? 'error' : '';
    }
    function visible(el) {
      const rect = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      return !!el.getClientRects().length && rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
    }
    function text(el) { return (el.innerText || el.textContent || '').trim(); }
    function stopPick() {picking = null;highlight.style.display = 'none';}
    document.addEventListener('mousemove', event => {
      if (!picking || event.composedPath().includes(host)) {highlight.style.display = 'none';return;}
      const box = event.target.getBoundingClientRect();
      Object.assign(highlight.style, {display:'block',top:`${box.top}px`,left:`${box.left}px`,width:`${box.width}px`,height:`${box.height}px`});
    }, true);
    document.addEventListener('click', event => {
      if (!picking || event.composedPath().includes(host)) return;
      event.preventDefault();event.stopImmediatePropagation();
      const field = picking;
      const el = event.target;
      const value = text(el);
      stopPick();
      if (!value || value.length > 300) {message('Pick a smaller element containing only the desired field.', true);return;}
      refs[field] = el;
      $(field).value = value;
      $('reviewed').checked = false;
      message(`Picked ${field}. Preview and review before saving.`);
    }, true);
    document.addEventListener('keydown', event => {if(event.key === 'Escape') stopPick();}, true);
    ui.querySelectorAll('[data-pick]').forEach(button => button.onclick = () => {
      picking = button.dataset.pick;
      message(`Click the ${picking} text on the menu. The click will read text without activating the site's button. Escape cancels.`);
    });
    ['category','name','variant','price'].forEach(field => $(field).oninput = () => {
      delete refs[field];$('reviewed').checked = false;
    });
    $('cancelpick').onclick = () => {stopPick();message('Pick canceled.');};
    $('minimize').onclick = () => {
      $('body').classList.toggle('hidden');
      $('minimize').textContent = $('body').classList.contains('hidden') ? 'Show' : 'Hide';
      stopPick();
    };
    async function send(payload) {
      try {
        let result = await window.__dpcCapture(payload);
        const deadline = Date.now()+65000;
        while(result.pending && result.request_id) {
          if(Date.now()>deadline) {message('Teaching save took too long. Check the app activity log.',true);return null;}
          await new Promise(resolve=>setTimeout(resolve,200));
          result = await window.__dpcTrainingResult(result.request_id);
        }
        if (!result.ok) {message(result.error, true);return null;}
        if (result.count !== undefined) $('count').textContent = result.count;
        return result;
      } catch(error) {message(`Could not save: ${error.message}`, true);return null;}
    }
    $('verified').onchange = () => {confirmed = false;};
    $('confirm').onclick = async () => {
      const result = await send({action:'confirm',checked:$('verified').checked});
      if(result) {confirmed=true;message('Store and channel confirmed by you for this page. Pick menu fields next.');}
    };
    function showPreview(rows) {
      preview = rows;
      $('reviewed').checked = false;
      $('preview').replaceChildren();
      if(!rows.length) return;
      const table = document.createElement('table');
      const header = table.insertRow();
      ['Select','Category','Item','Size/variant','USD price'].forEach(label => {
        const cell=document.createElement('th');cell.textContent=label;header.appendChild(cell);
      });
      rows.forEach(row => {
        row.selected=false;
        const tr=table.insertRow();
        const check=document.createElement('input');check.type='checkbox';
        check.onchange=()=>{row.selected=check.checked;$('reviewed').checked=false;};
        tr.insertCell().appendChild(check);
        ['category','name','variant','price'].forEach(field => {
          const input=document.createElement('input');input.type='text';input.value=row[field];
          input.oninput=()=>{row[field]=input.value;$('reviewed').checked=false;};
          tr.insertCell().appendChild(input);
        });
      });
      $('preview').appendChild(table);
      message(`Previewing ${rows.length} rows. Review and correct fields, select rows, then check the review box.`);
    }
    function current() {
      return Object.fromEntries(['category','name','variant','price'].map(field=>[field,$(field).value.trim()]));
    }
    $('single').onclick=()=>showPreview([current()]);
    function absolutePath(el) {
      const parts=[];
      while(el && el.nodeType===1) {
        const tag=el.tagName.toLowerCase();
        if(el===document.documentElement) {parts.unshift(tag);break;}
        const siblings=Array.from(el.parentElement.children).filter(child=>child.tagName===el.tagName);
        parts.unshift(`${tag}:nth-of-type(${siblings.indexOf(el)+1})`);
        el=el.parentElement;
      }
      return parts.join(' > ');
    }
    function pathWithin(root, el) {
      if (!root.contains(el) || root===el) return null;
      const parts=[];
      while(el!==root) {
        const siblings=Array.from(el.parentElement.children).filter(child=>child.tagName===el.tagName);
        parts.unshift(`${el.tagName.toLowerCase()}:nth-of-type(${siblings.indexOf(el)+1})`);
        el=el.parentElement;
      }
      return ':scope > '+parts.join(' > ');
    }
    $('similar').onclick=()=>{
      const name=refs.name,price=refs.price;
      if(!name?.isConnected || !price?.isConnected || name.contains(price) || price.contains(name)) {
        message('Pick separate name and price elements from the SAME menu card first.', true);return;
      }
      let root=name.parentElement;
      while(root && !root.contains(price)) root=root.parentElement;
      if(!root || ['BODY','HTML','MAIN'].includes(root.tagName)) {
        message('The selected fields do not share a small item card. Use Preview this item instead.',true);return;
      }
      const rootSelector=root.tagName.toLowerCase()+Array.from(root.classList).map(c=>'.'+CSS.escape(c)).join('');
      const namePath=pathWithin(root,name),pricePath=pathWithin(root,price);
      const candidates=Array.from(document.querySelectorAll(rootSelector)).filter(el=>!host.contains(el) && visible(el));
      if(candidates.length>500) {message('Too many candidate cards. Use individual capture instead.',true);return;}
      const defaults=current();
      const categoryPath=refs.category?.isConnected ? pathWithin(root,refs.category) : null;
      const variantPath=refs.variant?.isConnected ? pathWithin(root,refs.variant) : null;
      const rows=[];
      for(const card of candidates) {
        const n=card.querySelector(namePath),p=card.querySelector(pricePath);
        if(!n || !p || !visible(n) || !visible(p)) continue;
        const value=text(p);
        if(!/^\$?\s*\d+(?:\.\d{1,2})?$/.test(value)) continue;
        const categoryNode=categoryPath ? card.querySelector(categoryPath) : null;
        const variantNode=variantPath ? card.querySelector(variantPath) : null;
        const row={name:text(n),price:value,
          category:categoryPath ? (categoryNode ? text(categoryNode) : '') : defaults.category,
          variant:variantPath ? (variantNode ? text(variantNode) : '') : defaults.variant};
        if(row.name && row.name.length<=300 && row.category.length<=300 && row.variant.length<=300) rows.push(row);
      }
      if(!rows.length) {message('No exact visible prices found in similar cards. Use individual capture.',true);return;}
      showPreview(rows);
    };
    $('selectall').onclick=()=>{
      preview.forEach(row=>row.selected=true);
      $('preview').querySelectorAll('input[type=checkbox]').forEach(check=>check.checked=true);
      $('reviewed').checked=false;
    };
    $('clear').onclick=()=>{showPreview([]);message('Preview cleared. Saved rows are retained.');};
    $('save').onclick=async()=>{
      if(!confirmed || !$('verified').checked) {message('Confirm the store and channel first.',true);return;}
      const rows=preview.filter(row=>row.selected).map(({selected,...row})=>({...row,currency:'USD'}));
      $('save').disabled=true;
      const result=await send({action:'save',rows,reviewed:$('reviewed').checked});
      $('save').disabled=false;
      if(result) {showPreview([]);message(`Saved ${rows.length} reviewed rows. Continue collecting or Finish store.`);}
    };
    $('train').onclick=async()=>{
      if(!confirmed || !$('verified').checked) {message('Confirm this store first.',true);return;}
      if(!preview.length || !$('reviewed').checked) {message('Preview and review the page rows first.',true);return;}
      for(const field of ['location','name','price','category','variant']) {
        if(!refs[field]?.isConnected || $(field).value.trim()!==text(refs[field])) {
          message(`Pick the visible ${field} text from the page before teaching. Typed corrections are not replayable selectors.`,true);return;
        }
      }
      if(refs.name.contains(refs.price) || refs.price.contains(refs.name)) {
        message('Pick separate name and price elements in one item card.',true);return;
      }
      let root=refs.name.parentElement;
      while(root && !root.contains(refs.price)) root=root.parentElement;
      if(!root || ['BODY','HTML','MAIN'].includes(root.tagName)) {
        message('Pick name and price from the same small item card.',true);return;
      }
      const recipe={
        location_selector:absolutePath(refs.location),expected_location:text(refs.location),
        item_selector:root.tagName.toLowerCase()+Array.from(root.classList).map(c=>'.'+CSS.escape(c)).join(''),
        name_selector:pathWithin(root,refs.name),price_selector:pathWithin(root,refs.price)
      };
      for(const field of ['category','variant']) {
        const relative=pathWithin(root,refs[field]);
        if(relative) recipe[field+'_selector']=relative;
        else {recipe[field+'_global_selector']=absolutePath(refs[field]);recipe['expected_'+field]=text(refs[field]);}
      }
      $('train').disabled=true;
      const result=await send({action:'train',recipe,reviewed:$('reviewed').checked,
        reviewed_rows:preview.map(({selected,...row})=>row)});
      $('train').disabled=false;
      if(result) message(`Saved for autorun: ${result.page_count} page(s), ${result.item_count} items on this page. Teach other pages or Finish teaching.`);
    };
    $('finish').onclick=async()=>{
      if(preview.length && !window.confirm('There are unsaved preview rows. Finish without saving them?')) return;
      if(await send({action:'finish'})) message('Store finished. The next store will open, or Excel will be saved.');
    };
    $('skip').onclick=async()=>{
      if(!window.confirm('Skip this store without collecting prices?')) return;
      if(await send({action:'skip'})) message('Store skipped.');
    };
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',install,{once:true});
  else install();
})();
