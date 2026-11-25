/* Progressive, dependency-free enhancements shared by all FABRIX pages. */
(()=>{
  'use strict';
  document.querySelectorAll('.site-header').forEach(header=>{
    const menu=header.querySelector('#menu-toggle');
    const nav=header.querySelector('#category-nav');
    if(menu && nav){
      document.addEventListener('keydown', e=>{
        if(e.key==='Escape' && nav.classList.contains('open')){
          nav.classList.remove('open');menu.setAttribute('aria-expanded','false');menu.focus();
        }
      });
    }
  });
  const button=document.createElement('button');
  button.type='button';button.className='back-to-top';
  button.setAttribute('aria-label','Back to top');button.title='Back to top';button.textContent='↑';
  button.addEventListener('click',()=>window.scrollTo({top:0,behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'}));
  document.body.appendChild(button);
  const update=()=>button.classList.toggle('visible',window.scrollY>550);
  window.addEventListener('scroll',update,{passive:true}); update();
  document.addEventListener('keydown',e=>{
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){
      const search=document.getElementById('search-input');
      if(search){e.preventDefault();search.focus();search.select();}
    }
  });
  document.querySelectorAll('.app-form input[required],.app-form textarea[required]').forEach(el=>{
    el.addEventListener('invalid',()=>el.setAttribute('aria-invalid','true'));
    el.addEventListener('input',()=>{if(el.validity.valid)el.removeAttribute('aria-invalid');});
  });
  const current=location.pathname.split('/').pop()||'index.html';
  document.querySelectorAll('.app-nav a[href]').forEach(a=>{
    if(a.getAttribute('href')===current)a.setAttribute('aria-current','page');
  });
})();
