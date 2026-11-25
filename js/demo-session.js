"use strict";
// UI-only sign-out. No real authentication, sessions or authorization exist in the static demo.
(()=>{
 const KEY='fabrix2-demo-v6';
 let current;try{current=JSON.parse(localStorage.getItem(KEY)||'{}')?.user}catch{current=null}
 if(!current?.email)return;
 const nav=document.querySelector('.actions');if(!nav)return;
 const btn=document.createElement('button');btn.type='button';btn.className='action fabrix-signout';btn.textContent='Sign out';btn.setAttribute('aria-label','Sign out of local demo');btn.title='Signed in as '+current.email;
 btn.addEventListener('click',()=>{
  let state;try{state=JSON.parse(localStorage.getItem(KEY)||'{}')}catch{state={}}
  // Keep user-scoped records in their saved demo profile. Do not treat this as a secure session.
  state.user=null;state.addresses=[];state.orders=[];state.drafts=[];state.reports=[];state.reviews=[];state.notifications=[];
  state.store={name:'Your Handmade Studio',story:'',state:'Draft',notes:''};
  localStorage.setItem(KEY,JSON.stringify(state));
  localStorage.removeItem('fabrix-cart');localStorage.removeItem('fabrix-favorites');
  location.href='auth.html?mode=signin';
 });
 nav.append(btn);
})();
