'use strict';
// Shared navigation integration for the original six Figma-based pages.
(()=>{
 const resolve=(x)=>new URL(x,location.href).href;
 document.querySelectorAll('#account-nav').forEach(b=>b.addEventListener('click',e=>{e.preventDefault();e.stopImmediatePropagation();location.assign(resolve('account.html'));},true));
 document.querySelectorAll('.sell-link').forEach(a=>a.setAttribute('href','seller.html'));
 document.querySelectorAll('.footer-grid a').forEach(a=>{
  let v=a.textContent.trim().toLowerCase();
  if(v.includes('artisan dashboard')||v.includes('sell on fabrix')) a.href='seller.html';
  if(v.includes('help center')||v.includes('shipping')||v.includes('store standards')) a.href='help.html';
 });
  const footer=document.querySelector('.footer-grid');if(footer&&!footer.querySelector('.app-footer-links')){
   const d=document.createElement('div');d.className='app-footer-links';
   d.innerHTML='<h3>Your FABRIX</h3><a href="account.html">My account</a><a href="orders.html">My orders</a><a href="recommendations.html">Recommendations</a>';
   footer.append(d);
  }
  let admin=false;
  try{admin=JSON.parse(localStorage.getItem('fabrix-api-user')||'null')?.role==='admin'}catch{}
  if(admin){
   const footerLinks=document.querySelector('.app-footer-links');
   if(footerLinks)footerLinks.insertAdjacentHTML('beforeend','<a href="admin.html">Admin dashboard</a>');
  }else{
   document.querySelectorAll('a[href="admin.html"]').forEach(a=>a.remove());
  }
})();
