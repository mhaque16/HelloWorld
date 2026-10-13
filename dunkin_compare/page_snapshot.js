() => {
  const nodes = [];
  let counter = 0;
  const rendered = el => {
    const style=getComputedStyle(el),rect=el.getBoundingClientRect();
    return rect.width>0 && rect.height>0 && style.display!=='none' && style.visibility!=='hidden';
  };
  for(const el of document.querySelectorAll('body *')) {
    el.removeAttribute('data-dpc-ai');
  }
  const selector='button,a,input,select,[role="button"],[role="tab"],[role="radio"],h1,h2,h3,h4,label,span,p,div,address,strong,output';
  for(const el of document.querySelectorAll(selector)) {
    if(!rendered(el) || el.closest('#dpc-collector')) continue;
    const tag=el.tagName.toLowerCase(),type=(el.type||'').toLowerCase();
    if(tag==='input' && !['text','search','radio','checkbox'].includes(type)) continue;
    const sensitive=/password|credit.?card|card.?number|security.?code|email|phone|billing/i;
    if(tag==='input' && sensitive.test([el.name,el.id,el.autocomplete,el.placeholder].join(' '))) continue;
    const role=el.getAttribute('role')||'';
    const control=['button','a','input','select'].includes(tag)||['button','tab','radio'].includes(role);
    if(!control && !['h1','h2','h3','h4','label'].includes(tag) && el.children.length) continue;
    let text=(el.innerText||el.textContent||'').trim();
    if(tag==='select') text=Array.from(el.selectedOptions).map(o=>o.textContent.trim()).join(' ');
    if(!control && (!text || text.length>250)) continue;
    const id='e'+(++counter);
    el.setAttribute('data-dpc-ai',id);
    const ancestors=[];
    let parent=el;
    for(let i=0;parent&&i<5;i++,parent=parent.parentElement) ancestors.push(parent);
    const storeContext=ancestors.some(node=>node.tagName==='HEADER'||
      /selected.?store|your.?store|pickup.?location|selected.?location|order.?from/i.test([
        node.id,node.className,node.getAttribute('aria-label'),node.getAttribute('data-testid')].join(' ')));
    const interactiveParent=el.closest('button,a,[role="button"],[role="radio"],[role="tab"],label');
    const selected=!!el.checked||el.getAttribute('aria-pressed')==='true'||el.getAttribute('aria-selected')==='true'||
      el.getAttribute('aria-checked')==='true'||!!(interactiveParent && (
        interactiveParent.getAttribute('aria-checked')==='true'||interactiveParent.getAttribute('aria-selected')==='true'||
        interactiveParent.getAttribute('aria-pressed')==='true'||interactiveParent.querySelector('input:checked')));
    const rect=el.getBoundingClientRect();
    nodes.push({id,tag,role,type,text:text.slice(0,250),
      label:(el.getAttribute('aria-label')||el.labels?.[0]?.innerText||el.placeholder||text).trim().slice(0,200),
      value:tag==='input'&&['text','search'].includes(type)?el.value:'',
      href:tag==='a'?el.href:'',control,selected,store_context:storeContext,
      option_control:tag==='select'||type==='radio'||role==='radio'||!!(interactiveParent&&interactiveParent.getAttribute('role')==='radio'),
      interactive_parent:!!interactiveParent,
      on_screen:rect.bottom>0&&rect.top<innerHeight,
      options:tag==='select'?Array.from(el.options).map(o=>({value:o.value,label:o.textContent.trim(),disabled:o.disabled})):[]});
    if(nodes.length>=600) break;
  }
  return {url:location.href,title:document.title,elements:nodes,
    scroll_y:scrollY,scroll_height:document.documentElement.scrollHeight,viewport_height:innerHeight};
}
