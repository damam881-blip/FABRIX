'use strict';
/* FABRIX standalone demonstration. Browser localStorage is NOT authentication,
   authoritative checkout, reservation, payment, authorization or ML serving. */
(()=>{
const page=location.pathname.split('/').pop().replace('.html','');
const root=document.getElementById('app-root');
const KEY='fabrix2-demo-v6';
const get=(key,def)=>{try{const x=JSON.parse(localStorage.getItem(key));return x??def;}catch{return def;}};
const seed={user:null,addresses:[],orders:[],store:{name:'Your Handmade Studio',story:'',state:'Draft',notes:''},drafts:[],reports:[],reviews:[],notifications:[],adminStores:[],adminProducts:[],adminSellerOrders:[],sellerOrders:[],stats:null,personalization:true,consent:true};
let s={...seed,...get(KEY,{})};
if(window.FabrixAPI?.token()){
  try{
    const apiUser=JSON.parse(localStorage.getItem('fabrix-api-user')||'null');
    if(apiUser)s.user={...apiUser,name:apiUser.full_name,canShop:apiUser.can_shop,canSell:apiUser.can_sell};
  }catch{}
}
const ACCOUNT_STATES_KEY='fabrix-account-states-v1';
const scopedFields=['addresses','orders','store','drafts','reports','reviews','notifications','adminStores','adminProducts','adminSellerOrders','sellerOrders','stats','personalization','consent'];
const accountStates=()=>get(ACCOUNT_STATES_KEY,{});
function save(){
 localStorage.setItem(KEY,JSON.stringify(s));
 if(s.user?.email){let all=accountStates();all[s.user.email]=Object.fromEntries(scopedFields.map(k=>[k,s[k]]));localStorage.setItem(ACCOUNT_STATES_KEY,JSON.stringify(all));}
}
function switchToAccount(account,role){
 const saved=accountStates()[account.email]||{};
 s={...seed,...Object.fromEntries(scopedFields.map(k=>[k,saved[k]??seed[k]])),user:{name:account.name,email:account.email,canShop:true,canSell:!!account.canSell}};
 if(role==='artisan'&&account.canSell&&s.store.state==='Draft'&&!s.store.story.trim())s.store.notes='Complete your studio profile to request approval.';
 save();
}
async function signOut(){
 if(api())await api().logout().catch(()=>null);
 if(s.user?.email)save();
 s={...seed,user:null};
 localStorage.setItem(KEY,JSON.stringify(s));
 // Browser mock shopping state is intentionally cleared on account switch.
 localStorage.removeItem('fabrix-cart');
 localStorage.removeItem('fabrix-favorites');
 location.href='auth.html?mode=signin';
}

const cart=()=>get('fabrix-cart',{});
const setCart=v=>localStorage.setItem('fabrix-cart',JSON.stringify(v));
const fav=()=>get('fabrix-favorites',[]);
const $=id=>document.getElementById(id);
const money=n=>'$'+(Number(n)||0).toFixed(2);
const escape=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date=()=>new Date().toLocaleDateString('en-US',{year:'numeric',month:'short',day:'numeric'});
const uid=prefix=>prefix+'-'+Date.now().toString(36).toUpperCase()+'-'+Math.random().toString(36).slice(2,6).toUpperCase();
const api=()=>window.FabrixAPI?.enabled?window.FabrixAPI:null;
const apiRequest=(path,options={})=>{const client=api();if(!client)throw new Error('API unavailable');return client.request(path,options)};
const apiAddress=a=>({full_name:a.fullName,email:a.email,phone:a.phone||null,line1:a.street,line2:null,city:a.city,region:null,postal_code:a.postal,country:a.country||'US',is_default:false});
const syncFromAPI=()=>{if(window.FabrixAPI?.hydrated)Object.assign(s,window.FabrixAPI.hydrated)};
const sellerChildren=()=>api()?s.sellerOrders:s.orders.flatMap(o=>o.children);
const link=(href,label,secondary=false)=>`<a class="app-btn ${secondary?'outline':''}" href="${href}">${label}</a>`;
const status=x=>`<span class="app-status ${['Approved','Published','Delivered','Paid (demo)','Shipped'].includes(x)?'good':['Suspended','Changes Requested','Cancelled','Blocked'].includes(x)?'bad':''}">${escape(x)}</span>`;
const empty=(title,copy,href='products.html',label='Explore handmade')=>`<div class="app-panel app-empty"><h3>${title}</h3><p class="app-muted">${copy}</p>${link(href,label)}</div>`;
const notice=()=>api()?'<div class="app-note"><strong>API-backed demo:</strong> Identity, catalog, cart, checkout, orders, fulfillment and moderation use the local FastAPI service. Payments are sandbox-only.</div>':'<div class="app-note app-warning"><strong>Frontend demonstration:</strong> Data lives only in this browser. No real account authentication, payment, order placement, stock reservation, shipping request, or administrator authorization takes place.</div>';
const toast=message=>{const t=$('app-toast');if(!t)return;t.textContent=message;t.classList.remove('app-hidden');clearTimeout(toast.timer);toast.timer=setTimeout(()=>t.classList.add('app-hidden'),2800)};

function openConfirm(title,message,action){
 let dialog=document.getElementById('fabrix-confirm');
 if(!dialog){dialog=document.createElement('dialog');dialog.id='fabrix-confirm';dialog.className='app-confirm';document.body.append(dialog);}
 dialog.innerHTML=`<div class="app-panel"><div class="app-eyebrow">PLEASE CONFIRM</div><h2>${escape(title)}</h2><p class="app-muted">${escape(message)}</p><div class="app-actions"><button class="app-btn outline" id="confirm-keep">Keep as is</button><button class="app-btn danger" id="confirm-action">Confirm demo change</button></div></div>`;
 dialog.querySelector('#confirm-keep').onclick=()=>dialog.close();
 dialog.querySelector('#confirm-action').onclick=()=>{dialog.close();action()};
 dialog.showModal();
}

const validCart=()=>Object.entries(cart()).map(([id,qty])=>({product:products.find(p=>p.id===Number(id)),qty:Number(qty)})).filter(x=>x.product&&Number.isInteger(x.qty)&&x.qty>0&&x.qty<=x.product.stock);
const groups=items=>Object.groupBy?Object.groupBy(items,x=>x.product.maker):items.reduce((a,x)=>((a[x.product.maker]??=[]).push(x),a),{});
const rates={'Morrow Clay Studio':8,'Aster Metalworks':5,'Kindred Flame':6,'North Loop Knits':7,'Field Note Stitchery':7,'Thread & Timber':9};
const fee=items=>items.length?(rates[items[0].product.maker]??7):0; // illustrative per-seller shipping only
const cartTotals=items=>{let sellers=groups(items);return{items,subtotal:items.reduce((a,x)=>a+x.product.price*x.qty,0),shipping:Object.values(sellers).reduce((a,x)=>a+fee(x),0),sellers}};
const line=x=>`<div class="app-line"><a href="product.html?id=${x.product.id}" class="app-thumb" aria-label="View ${escape(x.product.name)}">✧</a><div><h3><a href="product.html?id=${x.product.id}">${escape(x.product.name)}</a></h3><small>${escape(x.product.maker)} · Qty ${x.qty}</small></div><strong>${money(x.product.price*x.qty)}</strong></div>`;
const userGuard=(next)=>{if(s.user)return false;location.href='auth.html?next='+encodeURIComponent(next);return true};
const notify=txt=>{s.notifications.unshift({message:txt,when:date()});s.notifications=s.notifications.slice(0,15);save()};
function initHeader(){
 document.querySelectorAll('#account-nav').forEach(n=>n.addEventListener('click',()=>location.href=s.user?'account.html':'auth.html'));
 document.querySelectorAll('#cart-nav').forEach(n=>n.addEventListener('click',()=>location.href='cart.html'));
 document.querySelectorAll('#favorites-nav').forEach(n=>n.addEventListener('click',()=>location.href='favorites.html'));
 document.querySelectorAll('#search-form').forEach(f=>f.addEventListener('submit',e=>{e.preventDefault();location.href='products.html?search='+encodeURIComponent(f.querySelector('input')?.value||'')}));
 $('menu-toggle')?.addEventListener('click',()=>{let n=$('category-nav');n?.classList.toggle('open');$('menu-toggle').setAttribute('aria-expanded',String(n?.classList.contains('open')))});
 document.querySelectorAll('#year').forEach(n=>n.textContent=new Date().getFullYear());
 const c=validCart().reduce((a,x)=>a+x.qty,0);document.querySelectorAll('#cart-count').forEach(n=>{n.textContent=c;n.classList.toggle('hidden',!c)});
 document.querySelectorAll('#favorite-count').forEach(n=>{n.textContent=fav().length;n.classList.toggle('hidden',!fav().length)});
}
function checkout(){let items=validCart();if(!items.length){root.innerHTML=empty('Your bag is empty','Add a piece before starting checkout.','products.html','Browse pieces');return}
 const t=cartTotals(items);let address=s.addresses[0]||{};
 root.innerHTML=`<div class="app-steps"><strong>Bag</strong> → <strong>Details</strong> → <span>Demo confirmation</span></div><div class="app-grid"><div class="app-stack"><section class="app-panel"><h2>Shipping information</h2><form class="app-form" id="checkout-form"><div class="app-two"><label>Full name <input name="fullName" required minlength="2" maxlength="90" autocomplete="name" value="${escape(address.fullName||s.user?.name||'')}"></label><label>Contact email <input name="email" required type="email" autocomplete="email" value="${escape(address.email||s.user?.email||'')}"></label></div><label>Phone number <input name="phone" required inputmode="tel" maxlength="25" autocomplete="tel" value="${escape(address.phone||'')}"></label><label>Street address <input name="street" required maxlength="120" autocomplete="street-address" value="${escape(address.street||'')}"></label><div class="app-two"><label>City <input name="city" required maxlength="70" value="${escape(address.city||'')}"></label><label>Country <input name="country" required maxlength="70" value="${escape(address.country||'')}"></label></div><label>Postal code <input name="postal" required maxlength="15" value="${escape(address.postal||'')}"></label><label class="app-check"><input type="checkbox" name="saveAddress" checked>Save this address in this browser for later demos</label><div class="app-separator"></div><h2>Demo payment</h2><label class="app-check"><input type="radio" name="payment" value="sandbox" checked>Sandbox payment preview — no card or real charge</label><p class="app-muted app-mini">Never enter real payment-card information in this prototype. The real backend must verify payment results and reserve stock atomically.</p><button class="app-btn" type="submit">Simulate order review →</button></form></section></div><aside class="app-panel"><div class="app-eyebrow">ORDER REVIEW</div><h2>Your makers</h2>${Object.entries(t.sellers).map(([seller,v])=>`<h3>${escape(seller)}</h3>${v.map(line).join('')}<div class="app-row app-mini"><span>Illustrative seller shipping</span><strong>${money(fee(v))}</strong></div><div class="app-separator"></div>`).join('')}<div class="app-row"><span>Items</span><strong>${money(t.subtotal)}</strong></div><div class="app-row"><span>Shipping (demo)</span><strong>${money(t.shipping)}</strong></div><div class="app-separator"></div><div class="app-row"><strong>Total estimate</strong><strong class="app-total">${money(t.subtotal+t.shipping)}</strong></div><p class="app-footnote">Seller-specific shipping is estimated on the frontend. Server validation is required in production.</p></aside></div>${notice()}`;
  $('checkout-form').addEventListener('submit',async e=>{
    e.preventDefault();
    if(userGuard('checkout.html'))return;
    const f=new FormData(e.target);
    let address=Object.fromEntries(['fullName','email','phone','street','city','country','postal'].map(k=>[k,String(f.get(k)||'').trim()]));
    if(Object.values(address).some(x=>!x)){toast('Please fill in all shipping fields');return}
    let fresh=validCart();
    if(fresh.length!==items.length){toast('Cart quantities changed, please review again');render();return}
    if(api()){
      const key=sessionStorage.getItem('fabrix-checkout-key')||uid('PAY');
      sessionStorage.setItem('fabrix-checkout-key',key);
      try{
        const result=await api().checkout({address:apiAddress(address),payment_method:'sandbox',shipping_method:'standard',idempotency_key:key,items:fresh.map(x=>({product_id:x.product.id,quantity:x.qty}))});
        await Promise.allSettled(fresh.map(x=>api().event(x.product.id,'PURCHASE',`buy-${key}-${x.product.id}`)));
        sessionStorage.removeItem('fabrix-checkout-key');
        await api().hydrate();
        syncFromAPI();
        setCart({});
        location.href='confirmation.html?id='+encodeURIComponent(result.id);
      }catch(err){toast(err.message||'Checkout failed. Please review your bag.')}
      return;
    }
    if(f.has('saveAddress'))s.addresses=[address,...s.addresses.filter(x=>x.street!==address.street) ].slice(0,5);
    let sum=cartTotals(fresh);let children=Object.entries(sum.sellers).map(([maker,lines])=>({id:uid('SELL'),maker,status:'Awaiting Processing',lines:lines.map(x=>({id:x.product.id,name:x.product.name,price:x.product.price,qty:x.qty})),shipping:fee(lines)}));let order={id:uid('DEMO'),owner:s.user.email,created:date(),address,subtotal:sum.subtotal,shipping:sum.shipping,total:sum.subtotal+sum.shipping,payment:'Paid (demo)',children};s.orders.unshift(order);save();setCart({});notify('Order '+order.id+' created in local demo mode');location.href='confirmation.html?id='+encodeURIComponent(order.id)
  })
}
function confirmation(){const id=new URLSearchParams(location.search).get('id');const o=s.orders.find(x=>x.id===id&&x.owner===s.user?.email);root.innerHTML=o?`<div class="app-wide app-panel"><div class="app-eyebrow">DEMO ORDER CONFIRMATION</div><h2>Thank you for discovering handmade.</h2><p class="app-muted">${api()?'Your order was recorded by the local backend with a sandbox payment. No external payment provider was contacted.':'A simulated order was saved to this browser. <strong>No real payment or order was sent.</strong>'}</p><div class="app-banner">Reference: <strong>${escape(o.id)}</strong> · ${o.children.length} seller order(s) · ${money(o.total)} ${api()?'total':'estimated total'}</div><p>Each maker's parcel appears separately in order tracking.</p><div class="app-actions">${link('order.html?id='+encodeURIComponent(o.id),'View order details')}${link('orders.html','My order history',true)}</div></div>${notice()}`:empty('No demo order found','Open your order history to view your saved demonstrations.','orders.html','View orders')}
function auth(){
 const params=new URLSearchParams(location.search), next=params.get('next');
 const safeNext=['checkout.html','account.html','orders.html','seller.html'].includes(next)?next:'account.html';
 const roles=['customer','artisan'];
 let mode=params.get('mode')==='register'?'register':'signin';
 let role=params.get('role')==='artisan'?'artisan':'customer';
 const ACCOUNTS_KEY='fabrix-demo-profiles-v1';
 const profiles=()=>get(ACCOUNTS_KEY,{});
 const heading=()=>mode==='signin'?'Welcome back.':'Make something meaningful.';
 function draw(){
   const existing=s.user;
   root.innerHTML=`<div class="identity-layout"><aside class="identity-story"><span class="eyebrow">A HOME FOR THE HANDMADE</span><h2>Made by people.<br><em>Found by you.</em></h2><p>Discover thoughtfully made objects, or share the pieces you create with people who value your craft.</p><div class="identity-story-note">✦ One FABRIX identity can shop and run an artisan studio.</div></aside><section class="identity-panel"><div class="app-eyebrow">FABRIX • LOCAL PREVIEW</div><h2>${heading()}</h2><p class="app-muted">Choose how you want to continue. Buyer and maker experiences use the same email and account.</p><div class="identity-mode" role="group" aria-label="Account action"><button type="button" class="${mode==='signin'?'active':''}" data-mode="signin" aria-pressed="${mode==='signin'}">Sign in</button><button type="button" class="${mode==='register'?'active':''}" data-mode="register" aria-pressed="${mode==='register'}">Create account</button></div><div class="identity-role-caption">I want to...</div><div class="identity-role-grid"><button type="button" class="identity-role ${role==='customer'?'active':''}" data-role="customer" aria-pressed="${role==='customer'}"><span class="identity-role-icon">♡</span><strong>Shop handmade</strong><small>Explore, save pieces and track your orders</small></button><button type="button" class="identity-role ${role==='artisan'?'active':''}" data-role="artisan" aria-pressed="${role==='artisan'}"><span class="identity-role-icon">✳</span><strong>Sell my craft</strong><small>Build your studio and manage your work</small></button></div><form id="identity-form" class="app-form identity-form">${mode==='register'?`<label>Full name<input name="name" autocomplete="name" required minlength="2" maxlength="80" placeholder="Your name" value="${escape(existing?.name||'')}"></label>`:''}<label>Email address<input name="email" autocomplete="email" type="email" required placeholder="you@example.com" value="${escape(existing?.email||'')}"></label><label>Password <input name="password" type="password" autocomplete="${mode==='register'?'new-password':'current-password'}" minlength="8" maxlength="72" placeholder="8+ characters for API accounts"></label>${mode==='register'&&role==='artisan'?`<div class="identity-artisan-note">Your artisan studio starts as a <strong>Draft</strong>. You can prepare listings immediately; selling requires Admin approval.</div><label>Studio name<input name="studioName" required minlength="2" maxlength="80" placeholder="Your handmade studio"></label><label>Tell us about your craft <textarea name="studioStory" required minlength="10" maxlength="800" rows="3" placeholder="Your materials, techniques and story"></textarea></label>`:''}${mode==='register'?`<label class="app-check"><input type="checkbox" name="consent">Use my permitted shopping activity for personalized discoveries (optional)</label>`:''}<button class="app-btn identity-submit" type="submit">${mode==='signin'?'Continue to my account':role==='artisan'?'Create account & studio draft':'Create customer account'} <span>→</span></button><p class="identity-disclaimer"><strong>Demo only:</strong> With the API running, this password is verified by the local backend; otherwise the browser-local profile is used. Never reuse a real password.</p></form>${existing?`<div class="identity-current">Current preview: <strong>${escape(existing.email)}</strong> · <button id="identity-logout" type="button">Sign out</button></div>`:''}</section></div>`;
   root.querySelectorAll('[data-mode]').forEach(btn=>btn.onclick=()=>{mode=btn.dataset.mode;draw()});
   root.querySelectorAll('[data-role]').forEach(btn=>btn.onclick=()=>{role=btn.dataset.role;draw()});
   $('identity-logout')?.addEventListener('click',signOut);
   $('identity-form').addEventListener('submit',async e=>{
      e.preventDefault();const data=new FormData(e.currentTarget);
      const email=String(data.get('email')||'').trim().toLowerCase();
      if(!email){toast('Enter an email address');return}
      const password=String(data.get('password')||'');
      if(api()){
        if(mode==='register'&&password.length<8){toast('Use a password of at least 8 characters');return}
        if(mode==='signin'&&!password){toast('Enter your password');return}
        try{
          if(mode==='register'){
            await api().register({email,password,full_name:String(data.get('name')||'').trim()||'FABRIX Customer',role:role==='artisan'?'artisan':'customer',studio_name:String(data.get('studioName')||'').trim()||null,studio_story:String(data.get('studioStory')||'').trim()||null,consent:data.has('consent'),personalization:data.has('consent')});
          }else{
            await api().login({email,password});
          }
          await api().migrateLocalState();
          await api().hydrate();
          syncFromAPI();
          location.href=role==='artisan'?'seller.html':safeNext;
        }catch(err){toast(err.message||'Sign-in failed. Check your email and password.')}
        return;
      }
      const people=profiles(); let account=people[email];
      if(mode==='register'){
        if(account){toast('This email already has a local demo profile. Choose Sign in.');return}
        account={name:String(data.get('name')||'').trim(),email,canShop:true,canSell:role==='artisan'};
        if(role==='artisan'){const all=accountStates();all[email]={...Object.fromEntries(scopedFields.map(k=>[k,seed[k]])),store:{name:String(data.get('studioName')||'').trim(),story:String(data.get('studioStory')||'').trim(),state:'Draft',notes:''},consent:data.has('consent'),personalization:data.has('consent')};localStorage.setItem(ACCOUNT_STATES_KEY,JSON.stringify(all));}
        if(role!=='artisan'){const all=accountStates();all[email]={...Object.fromEntries(scopedFields.map(k=>[k,seed[k]])),consent:data.has('consent'),personalization:data.has('consent')};localStorage.setItem(ACCOUNT_STATES_KEY,JSON.stringify(all));}
        people[email]=account;localStorage.setItem(ACCOUNTS_KEY,JSON.stringify(people));
      }else{
        if(!account){toast('No local demo profile found. Choose Create account first.');return}
        if(role==='artisan'&&!account.canSell){
          // Retain one identity: enable artisan draft capabilities without creating a second login.
          account.canSell=true;people[email]=account;localStorage.setItem(ACCOUNTS_KEY,JSON.stringify(people));
          const all=accountStates();all[email]={...(all[email]||{}),store:{name:'Your Handmade Studio',story:'',state:'Draft',notes:'Complete your studio profile to request approval.'}};localStorage.setItem(ACCOUNT_STATES_KEY,JSON.stringify(all));
        }
      }
      switchToAccount(account,role);
      location.href=role==='artisan'?'seller.html':safeNext;
   });
 }
 draw();
}
function account(){if(userGuard('account.html'))return;root.innerHTML=`<nav class="app-nav"><a href="account.html" aria-current="page">Profile</a><a href="orders.html">My orders</a><a href="favorites.html">Saved pieces</a><a href="seller.html">Artisan workspace</a><button class="app-btn outline" type="button" id="account-sign-out">Sign out ↗</button></nav><div class="app-grid"><div class="app-stack"><section class="app-panel"><h2>My profile</h2><form id="profile-form" class="app-form"><label>Display name<input name="name" value="${escape(s.user.name)}" required maxlength="80"></label><label>Account email (demo identifier)<input value="${escape(s.user.email)}" readonly></label><button class="app-btn" type="submit">Save profile</button></form></section><section class="app-panel"><div class="app-row"><h2>Saved addresses</h2><button class="app-btn outline" id="add-address">Add address</button></div><div id="addresses">${s.addresses.length?s.addresses.map((x,i)=>`<div class="app-row"><p>${escape(x.fullName)} · ${escape(x.street)}, ${escape(x.city)}, ${escape(x.country)}</p><button class="app-btn text" data-remove-address="${i}">Remove</button></div>`).join(''): '<p class="app-muted">No saved addresses yet.</p>'}</div><form id="address-form" class="app-form app-hidden"><div class="app-two"><label>Recipient <input name="fullName" required value="${escape(s.user.name)}"></label><label>Email <input type="email" name="email" required value="${escape(s.user.email)}"></label></div><label>Phone <input name="phone" required></label><label>Street <input name="street" required></label><div class="app-two"><label>City <input name="city" required></label><label>Country <input name="country" required></label></div><label>Postal code <input name="postal" required></label><button class="app-btn">Save address locally</button></form></section></div><div class="app-stack"><section class="app-panel soft"><h2>Shopping privacy</h2><label class="app-check"><input type="checkbox" id="personalization" ${s.personalization?'checked':''}>Enable personalized recommendations (demo)</label><p class="app-muted app-mini">With this switched off, only general discovery appears. No actual ML data is collected or sent to a service in this static build.</p><button class="app-btn outline" id="clear-preferences">Clear local shopping preferences</button></section><section class="app-panel"><h2>Updates</h2>${s.notifications.length?s.notifications.slice(0,5).map(n=>`<p class="app-muted app-mini">${escape(n.when)} · ${escape(n.message)}</p>`).join(''):'<p class="app-muted">No local notifications.</p>'}</section>${link('orders.html','View order history')}</div></div>${notice()}`;
  $('account-sign-out').onclick=signOut;
  $('profile-form').onsubmit=async e=>{
    e.preventDefault();
    const name=String(new FormData(e.target).get('name')||'').trim();
    if(api()){
      try{
        await apiRequest('/users/me',{method:'PATCH',body:{full_name:name}});
        await api().hydrate();syncFromAPI();toast('Profile saved');
      }catch(err){toast(err.message||'Profile could not be saved')}
      return;
    }
    s.user.name=name;(()=>{let people=get('fabrix-demo-profiles-v1',{});if(people[s.user.email]){people[s.user.email].name=s.user.name;localStorage.setItem('fabrix-demo-profiles-v1',JSON.stringify(people))}})();save();toast('Profile updated locally')
  };
  $('add-address').onclick=()=>$('address-form').classList.toggle('app-hidden');
  $('address-form').onsubmit=async e=>{
    e.preventDefault();
    const f=new FormData(e.target);
    const address=Object.fromEntries(['fullName','email','phone','street','city','country','postal'].map(k=>[k,String(f.get(k)||'').trim()]));
    if(api()){
      try{
        await apiRequest('/users/me/addresses',{method:'POST',body:apiAddress(address)});
        await api().hydrate();syncFromAPI();render();toast('Address saved');
      }catch(err){toast(err.message||'Address could not be saved')}
      return;
    }
    s.addresses.push(address);save();render()
  };
  root.querySelectorAll('[data-remove-address]').forEach(b=>b.onclick=async()=>{
    const index=Number(b.dataset.removeAddress);
    if(api()&&s.addresses[index]?.id){
      try{
        await apiRequest('/users/me/addresses/'+s.addresses[index].id,{method:'DELETE'});
        await api().hydrate();syncFromAPI();render();return;
      }catch(err){toast(err.message||'Address could not be removed');return}
    }
    s.addresses.splice(index,1);save();render()
  });
  $('personalization').onchange=async e=>{
    const checked=e.target.checked;s.personalization=checked;s.consent=checked;
    if(api()){
      try{
        await apiRequest('/users/me',{method:'PATCH',body:{personalization:checked,consent:checked}});
        await api().hydrate();syncFromAPI();toast('Preference saved');
      }catch(err){toast(err.message||'Preference could not be saved')}
      return;
    }
    save();toast('Preference saved locally')
  };
  $('clear-preferences').onclick=async()=>{
    if(api()){
      try{
        localStorage.setItem('fabrix-favorites','[]');
        await apiRequest('/users/me',{method:'PATCH',body:{personalization:false,consent:false}});
        await api().hydrate();syncFromAPI();render();toast('Favorites and personalization cleared');
      }catch(err){toast(err.message||'Preferences could not be cleared')}
      return;
    }
    localStorage.removeItem('fabrix-favorites');s.personalization=false;s.consent=false;save();render();toast('Favorites and personalization settings cleared locally')
  };
}
function orders(){if(userGuard('orders.html'))return;let data=s.orders.filter(x=>x.owner===s.user.email);root.innerHTML=`<nav class="app-nav"><a href="account.html">My account</a><a href="orders.html" aria-current="page">Order history</a><a href="favorites.html">Saved pieces</a></nav>${data.length?`<div class="app-stack">${data.map(o=>`<article class="app-panel"><div class="app-row"><div><div class="app-eyebrow">${escape(o.created)}</div><h3>${escape(o.id)}</h3><p class="app-muted">${o.children.length} maker(s) · ${money(o.total)} · Sandbox simulation</p></div>${link('order.html?id='+encodeURIComponent(o.id),'Track order')}</div>${o.children.map(c=>`<p class="app-row"><strong>${escape(c.maker)}</strong>${status(c.status)}</p>`).join('')}</article>`).join('')}</div>`:empty('No orders yet','Your local checkout previews will appear here.','products.html','Discover products')}${notice()}`}
function order(){if(userGuard('orders.html'))return;let o=s.orders.find(x=>x.id===new URLSearchParams(location.search).get('id')&&x.owner===s.user.email);if(!o){root.innerHTML=empty('Order not found','This order is not associated with your current local demo account.','orders.html','My orders');return}
 const states=o.children.map(x=>x.status);const parent=states.every(x=>x==='Delivered')?'Delivered':states.every(x=>x==='Cancelled')?'Cancelled':states.includes('Shipped')?'Partially shipped':states.includes('Processing')?'Processing':'Awaiting processing';
 root.innerHTML=`<div class="app-steps"><a href="orders.html">Orders</a> → <strong>${escape(o.id)}</strong></div><div class="app-grid"><div class="app-stack"><section class="app-panel"><div class="app-row"><div><div class="app-eyebrow">${escape(o.created)}</div><h2>Order overview</h2></div>${status(parent)}</div><p class="app-muted">One parent order with ${o.children.length} independently tracked seller order(s).</p>${o.children.map((c,i)=>`<div class="app-separator"></div><div class="app-row"><h3>${escape(c.maker)}</h3>${status(c.status)}</div>${c.lines.map(v=>line({product:{id:v.productId||v.id,name:v.name,maker:c.maker,price:v.price},qty:v.qty})).join('')}<div class="app-row"><span>Seller shipping (demo)</span><strong>${money(c.shipping)}</strong></div>${!['Shipped','Delivered','Cancelled'].includes(c.status)?`<button class="app-btn outline" data-cancel="${i}">Request demo cancellation</button>`:''}${c.status==='Delivered'?c.lines.map(l=>`<div class="app-row"><span>Review ${escape(l.name)}</span><button class="app-btn outline" data-review="${l.id}" data-child="${i}">Write review</button></div>`).join(''):''}`).join('')}</section></div><aside class="app-panel"><h2>Summary</h2><p class="app-row">Items <strong>${money(o.subtotal)}</strong></p><p class="app-row">Seller shipping <strong>${money(o.shipping)}</strong></p><div class="app-separator"></div><p class="app-row">Total <strong class="app-total">${money(o.total)}</strong></p><p class="app-muted app-mini">Delivery address: ${escape(o.address.street)}, ${escape(o.address.city)}</p><p class="app-muted app-mini">Payment: ${escape(o.payment)}</p></aside></div>${notice()}`;
  root.querySelectorAll('[data-cancel]').forEach(b=>b.onclick=()=>{
    const c=o.children[Number(b.dataset.cancel)];
    openConfirm('Cancel this seller order?',api()?'The local backend will cancel this seller order if it is still processing.':'This changes only the selected seller order in your local demo. No real cancellation or refund occurs.',async()=>{
      if(api()){
        try{
          await apiRequest('/orders/seller/'+encodeURIComponent(c.id)+'/cancel',{method:'POST'});
          await api().hydrate();syncFromAPI();render();return;
        }catch(err){toast(err.message||'Cancellation failed');return}
      }
      c.status='Cancelled';notify('Seller order '+c.id+' cancelled (demo)');save();render()
    })
  });
  root.querySelectorAll('[data-review]').forEach(b=>b.onclick=async()=>{
    const id=Number(b.dataset.review);
    const child=o.children[Number(b.dataset.child)];
    const key=o.id+':'+child.id+':'+id;
    if(s.reviews.some(r=>r.itemId===id||r.key===key)){toast('This delivered item was already reviewed');return}
    const rating=prompt('Rating (1–5):','5');if(rating===null)return;
    const n=Number(rating);if(!Number.isInteger(n)||n<1||n>5){toast('Choose a number from 1 to 5');return}
    const message=prompt('Write a short product review:','Thoughtfully made.');if(message===null)return;
    if(api()){
      try{
        await apiRequest('/reviews',{method:'POST',body:{order_item_id:id,rating:n,message:message.slice(0,300)}});
        await api().hydrate();syncFromAPI();render();toast('Review submitted');
      }catch(err){toast(err.message||'Review could not be submitted')}
      return;
    }
    s.reviews.push({key,productId:id,rating:n,message:message.slice(0,300),author:s.user.name});save();toast('Review saved locally')
  })
}
function seller(){if(userGuard('seller.html'))return;const store=s.store;
 root.innerHTML=`<nav class="app-nav"><a href="seller.html" aria-current="page">My studio</a><a href="account.html">Buyer account</a><a href="orders.html">My purchases</a></nav><div class="app-cols"><div class="app-kpi"><span class="app-eyebrow">STORE STATUS</span><strong style="font-size:24px">${escape(store.state)}</strong><span class="app-muted app-mini">Only admin demo actions can approve stores.</span></div><div class="app-kpi"><span class="app-eyebrow">MY LISTINGS</span><strong>${s.drafts.length}</strong><span class="app-muted app-mini">Draft or published demo listings</span></div><div class="app-kpi"><span class="app-eyebrow">SELLER ORDERS</span><strong>${sellerChildren().filter(c=>c.maker===store.name).length}</strong><span class="app-muted app-mini">Browser-local only</span></div></div><div class="app-grid app-section"><div class="app-stack"><section class="app-panel"><h2>Studio identity</h2><form id="store-form" class="app-form"><label>Store name <input name="name" required maxlength="80" value="${escape(store.name)}"></label><label>Your story <textarea name="story" maxlength="1200">${escape(store.story)}</textarea></label><div class="app-row"><button class="app-btn">Save studio draft</button><button id="store-submit" type="button" class="app-btn outline" ${!['Draft','Changes Requested'].includes(store.state)?'disabled':''}>Submit for approval</button></div><p class="app-muted app-mini">${escape(store.notes||'You can prepare drafts before your studio is approved.')}</p></form></section><section class="app-panel"><h2>My product listings</h2><form class="app-form" id="product-form"><label>Product name <input name="name" required maxlength="100"></label><label>Description <textarea name="description" required maxlength="700"></textarea></label><div class="app-two"><label>Category <select name="category" required><option>Ceramics</option><option>Jewelry</option><option>Fiber & textile</option><option>Home objects</option></select></label><label>Material <input name="material" required></label></div><div class="app-two"><label>Price (USD, demo) <input name="price" type="number" min="0.01" step="0.01" required></label><label>Stock <input name="stock" type="number" min="0" step="1" required></label></div><button class="app-btn">Create product draft</button></form><div class="app-separator"></div>${s.drafts.length?s.drafts.map((d,i)=>`<div class="app-row"><div><strong>${escape(d.name)}</strong><p class="app-muted app-mini">${money(d.price)} · ${d.stock} available · ${status(d.state)}</p></div><div class="app-actions">${d.state==='Draft'?`<button data-publish="${i}" class="app-btn outline" ${store.state!=='Approved'?'disabled':''}>Publish</button>`:''}<button data-unpublish="${i}" class="app-btn text" ${d.state!=='Published'?'disabled':''}>Unpublish</button></div></div>`).join(''):'<p class="app-muted">No product drafts yet.</p>'}</section></div><aside class="app-panel"><h2>Seller order fulfillment</h2>${sellerChildren().map(child=>({order:null,child})).filter(x=>x.child.maker===store.name).map(({order,child})=>`<div><strong>${escape(child.id)}</strong><p>${status(child.status)}</p>${child.lines.map(l=>`<p class="app-muted app-mini">${escape(l.name)} × ${l.qty}</p>`).join('')}<div class="app-actions">${child.status==='Awaiting Processing'?`<button class="app-btn outline" data-fulfill="${escape(child.id)}" data-next="Processing">Mark Processing</button>`:''}${child.status==='Processing'?`<button class="app-btn outline" data-fulfill="${escape(child.id)}" data-next="Shipped">Mark Shipped</button>`:''}</div></div><div class="app-separator"></div>`).join('')||'<p class="app-muted">No seller orders yet.</p>'}<p class="app-muted app-mini">Seller cannot mark Delivered. Admin confirms delivery in V1.</p></aside></div>${notice()}`;
  $('store-form').onsubmit=async e=>{
    e.preventDefault();
    const f=new FormData(e.target);
    const payload={name:String(f.get('name')).trim(),story:String(f.get('story')).trim(),craft:'Textiles'};
    if(api()){
      try{
        await apiRequest('/seller/store',{method:s.store.id?'PATCH':'POST',body:payload});
        await api().hydrate();syncFromAPI();render();toast('Studio saved');
      }catch(err){toast(err.message||'Studio could not be saved')}
      return;
    }
    store.name=payload.name;store.story=payload.story;save();toast('Studio draft saved locally')
  };
  $('store-submit').onclick=async()=>{
    if(!store.name.trim()||!store.story.trim()){toast('Complete studio identity and story first');return}
    if(api()){
      try{
        await apiRequest('/seller/store/submit',{method:'POST'});
        await api().hydrate();syncFromAPI();render();toast('Studio submitted for review');
      }catch(err){toast(err.message||'Studio could not be submitted')}
      return;
    }
    store.state='Pending';notify('Store application submitted for demo admin review');save();render()
  };
  $('product-form').onsubmit=async e=>{
    e.preventDefault();
    const f=new FormData(e.target);
    const payload={name:String(f.get('name')).trim(),description:String(f.get('description')).trim(),category:String(f.get('category')),material:String(f.get('material')).trim(),price:Number(f.get('price')),stock:Number(f.get('stock')),status:'Draft'};
    if(api()){
      try{
        await apiRequest('/products',{method:'POST',body:payload});
        await api().hydrate();syncFromAPI();render();toast('Product draft created');
      }catch(err){toast(err.message||'Product draft could not be created')}
      return;
    }
    s.drafts.push({id:uid('LIST'),...payload,state:'Draft'});save();render()
  };
  root.querySelectorAll('[data-publish]').forEach(b=>b.onclick=async()=>{
    if(store.state!=='Approved'){toast('Admin activation required');return}
    const draft=s.drafts[Number(b.dataset.publish)];
    if(api()){
      try{
        await apiRequest('/products/'+draft.id,{method:'PATCH',body:{status:'Published'}});
        await api().hydrate();syncFromAPI();render();return;
      }catch(err){toast(err.message||'Product could not be published');return}
    }
    draft.state='Published';save();render()
  });
  root.querySelectorAll('[data-unpublish]').forEach(b=>b.onclick=async()=>{
    const draft=s.drafts[Number(b.dataset.unpublish)];
    if(api()){
      try{
        await apiRequest('/products/'+draft.id,{method:'PATCH',body:{status:'Unpublished'}});
        await api().hydrate();syncFromAPI();render();return;
      }catch(err){toast(err.message||'Product could not be unpublished');return}
    }
    draft.state='Unpublished';save();render()
  });
  root.querySelectorAll('[data-fulfill]').forEach(b=>b.onclick=async()=>{
    const child=sellerChildren().find(c=>c.id===b.dataset.fulfill);
    const valid=(child?.status==='Awaiting Processing'&&b.dataset.next==='Processing')||(child?.status==='Processing'&&b.dataset.next==='Shipped');
    if(!valid)return;
    if(api()){
      try{
        await apiRequest('/orders/seller/'+encodeURIComponent(child.id)+'/status?next_status='+encodeURIComponent(b.dataset.next),{method:'PATCH'});
        await api().hydrate();syncFromAPI();render();
      }catch(err){toast(err.message||'Status could not be updated')}
      return;
    }
    child.status=b.dataset.next;save();render()
  })}
function admin(){
 if(api()&&s.user?.role!=='admin'){root.innerHTML=empty('Admin access required','Sign in with the seeded admin account to use server-authorized moderation.','auth.html','Admin sign in');return}
 const stores=api()?s.adminStores:[s.store];
 const products=api()?s.adminProducts:s.drafts;
 const sellerOrders=api()?s.adminSellerOrders:s.orders.flatMap(o=>o.children);
 const reports=s.reports||[];
 const store=stores[0]||s.store;
 const pendingStores=s.stats?.pending_stores??stores.filter(x=>x.state==='Pending').length;
 const orderCount=s.stats?.orders??s.orders.length;
 root.innerHTML=`${notice()}<div class="app-banner"><strong>${api()?'Server-authorized admin mode:':'Admin simulation mode:'}</strong> ${api()?'Store decisions, product moderation, delivery confirmations and report resolution are checked by the local backend and written to its database.':'This static demo does not grant genuine admin privileges. Production actions must be server-authorized and audited.'}</div><div class="app-cols app-section"><div class="app-kpi"><span class="app-eyebrow">PENDING STORES</span><strong style="font-size:24px">${pendingStores}</strong></div><div class="app-kpi"><span class="app-eyebrow">ORDER RECORDS</span><strong>${orderCount}</strong></div><div class="app-kpi"><span class="app-eyebrow">REPORTED REVIEWS</span><strong>${reports.length}</strong></div></div><div class="app-grid"><div class="app-stack"><section class="app-panel"><h2>Store applications</h2><p class="app-muted">${escape(store.name)} · ${status(store.state)}</p><p class="app-muted app-mini">${escape(store.story||'No story provided yet.')}</p>${store.id?`<p class="app-mini">Studio #${escape(store.id)}</p>`:''}<label class="app-form">Decision rationale <input class="app-input" id="admin-reason" placeholder="Reason for admin decision"></label><div class="app-actions" style="margin-top:15px"><button class="app-btn" data-store-decision="Approved">Approve</button><button class="app-btn outline" data-store-decision="Changes Requested">Request changes</button><button class="app-btn danger" data-store-decision="Suspended">Suspend</button></div><p class="app-muted app-mini">Approved studios may publish valid drafts; approval never auto-publishes products.</p></section><section class="app-panel"><h2>Product moderation</h2>${products.length?products.map((d,i)=>`<div class="app-row"><span>${escape(d.name)} · ${status(d.state)}</span><button class="app-btn outline" data-block="${i}">${d.state==='Blocked'?'Unblock':'Block'}</button></div>`).join(''):'<p class="app-muted">No artisan listings available.</p>'}</section><section class="app-panel"><h2>Review reports</h2>${reports.length?reports.map((r,i)=>`<div class="app-row"><span>${escape(r.reason)} · ${status(r.status)}</span><span class="app-actions"><button class="app-btn outline" data-report="${i}" data-decision="kept">Keep</button><button class="app-btn text" data-report="${i}" data-decision="removed">Remove</button><button class="app-btn text" data-report="${i}" data-decision="dismissed">Dismiss</button></span></div>`).join(''):'<p class="app-muted">No pending reports.</p>'}</section></div><aside class="app-panel"><h2>Delivery confirmation</h2>${sellerOrders.map(c=>`<div class="app-row"><div><strong>${escape(c.maker)}</strong><p class="app-mini">${escape(c.id)} · ${status(c.status)}</p></div><button class="app-btn outline" data-deliver="${escape(c.id)}" ${c.status!=='Shipped'?'disabled':''}>Confirm delivered</button></div><div class="app-separator"></div>`).join('')||'<p class="app-muted">No seller orders.</p>'}<h3>Operational notes</h3><p class="app-muted app-mini">Payments are sandbox-only. All admin decisions are recorded in the backend audit log when the API is active.</p></aside></div>`;
 root.querySelectorAll('[data-store-decision]').forEach(b=>b.onclick=async()=>{
   const action=b.dataset.storeDecision;
   const reason=$('admin-reason')?.value.trim()||'';
   if(!reason){toast('A decision reason is required');return}
   if(api()){
     if(!store.id){toast('No server store record available');return}
     try{
       await apiRequest('/admin/stores/'+store.id,{method:'PATCH',body:{decision:action,reason}});
       await api().hydrate();syncFromAPI();render();
     }catch(err){toast(err.message||'Store decision failed')}
     return;
   }
   const valid=(store.state==='Pending'&&['Approved','Changes Requested'].includes(action))||(store.state==='Approved'&&action==='Suspended')||(store.state==='Suspended'&&['Approved','Changes Requested'].includes(action));
   if(!valid){toast('Invalid store lifecycle transition');return}
   store.state=action;store.notes=reason;notify('Demo admin decision: '+action+' — '+store.notes);save();render()
 });
 root.querySelectorAll('[data-block]').forEach(b=>b.onclick=async()=>{
   const d=products[Number(b.dataset.block)];const next=d.state==='Blocked'?'Unpublished':'Blocked';
   if(api()){
     try{
       await apiRequest('/products/'+d.id,{method:'PATCH',body:{status:next}});
       await api().hydrate();syncFromAPI();render();
     }catch(err){toast(err.message||'Product moderation failed')}
     return;
   }
   d.state=next;save();render()
 });
 root.querySelectorAll('[data-deliver]').forEach(b=>b.onclick=async()=>{
   const c=sellerOrders.find(x=>x.id===b.dataset.deliver);
   if(c?.status!=='Shipped')return;
   if(api()){
     try{
       await apiRequest('/orders/seller/'+encodeURIComponent(c.id)+'/status?next_status=Delivered',{method:'PATCH'});
       await api().hydrate();syncFromAPI();render();
     }catch(err){toast(err.message||'Delivery confirmation failed')}
     return;
   }
   c.status='Delivered';notify('Demo admin confirmed seller order '+c.id+' Delivered');save();render()
 });
 root.querySelectorAll('[data-report]').forEach(b=>b.onclick=async()=>{
   const r=reports[Number(b.dataset.report)];const decision=b.dataset.decision;
   if(api()){
     try{
       await apiRequest('/admin/reviews/reports/'+r.id+'?decision='+decision,{method:'PATCH'});
       await api().hydrate();syncFromAPI();render();
     }catch(err){toast(err.message||'Report decision failed')}
     return;
   }
   s.reports=s.reports.filter(x=>x!==r);save();render()
 });
}
async function recommendations(){
 const personalized=Boolean(s.personalization&&s.user&&s.consent);
 if(api()){
   try{
     const data=await apiRequest('/recommendations?limit=9');
     const shown=data.items.map(r=>({id:r.id,name:r.name,maker:r.artisan,price:r.price,category:r.category,reason:r.reason}));
     root.innerHTML=`<div class="app-banner">${personalized?'Personalized discoveries use permitted shopping signals from the local API and respect eligibility filters.':'General discovery from the API: no personalization signals are used.'}</div><div class="app-row app-section"><h2>${personalized?'For your collection':'Discover handmade pieces'}</h2><a class="app-btn outline" href="account.html">Privacy settings</a></div><div class="app-cols">${shown.map(p=>`<article class="app-product"><a href="product.html?id=${p.id}"><div class="app-card-visual"></div></a><div><span class="app-eyebrow">${escape(p.category)}</span><h3>${escape(p.name)}</h3><small>${escape(p.maker)}</small></div><div class="app-row"><strong>${money(p.price)}</strong><span class="app-chip">${escape(p.reason)}</span></div>${link('product.html?id='+p.id,'View piece')}</article>`).join('')}</div>${notice()}`;
     return;
   }catch{/* Fall back to local discovery below. */}
 }
 let ids=fav();let favorites=products.filter(x=>ids.includes(x.id));let ranked=[...products].sort((a,b)=>{if(!personalized)return a.id-b.id;return (favorites.some(x=>x.category===b.category)?1:0)-(favorites.some(x=>x.category===a.category)?1:0)||a.id-b.id});let shown=ranked.slice(0,9);
 root.innerHTML=`<div class="app-banner">${personalized?'Shopping signals demonstration: prioritizing categories from locally saved products.':'General discovery: diverse catalog selection without personalization.'} <strong>This is not an ML model.</strong></div><div class="app-row app-section"><h2>${personalized?'For your collection':'Discover handmade pieces'}</h2><a class="app-btn outline" href="account.html">Privacy settings</a></div><div class="app-cols">${shown.map(p=>`<article class="app-product"><a href="product.html?id=${p.id}"><div class="app-card-visual"></div></a><div><span class="app-eyebrow">${escape(p.category)}</span><h3>${escape(p.name)}</h3><small>${escape(p.maker)}</small></div><div class="app-row"><strong>${money(p.price)}</strong><span class="app-chip">${personalized&&favorites.some(f=>f.category===p.category)?'Similar saved category':'General pick'}</span></div>${link('product.html?id='+p.id,'View piece')}</article>`).join('')}</div>${notice()}`
}
function help(){root.innerHTML=`<div class="app-grid"><div class="app-stack"><section class="app-panel"><h2>How does FABRIX work?</h2><p class="app-muted">FABRIX is a marketplace for physical handmade products from independent artisan studios. Customers discover work, save favorites, check out through one unified cart, and track each seller’s fulfillment independently.</p></section><section class="app-panel"><h2>Payments & shipping</h2><p class="app-muted">The local API computes per-seller shipping, verifies stock atomically, records sandbox payments and uses 15-minute inventory reservations. No external payment provider is contacted.</p></section><section class="app-panel"><h2>Reviews & recommendations</h2><p class="app-muted">Verified reviews are limited to eligible delivered order items. The local FastAPI service serves consent-aware recommendations with eligibility and dismissal filtering.</p></section></div><aside class="app-panel"><h2>Quick links</h2><div class="app-stack">${link('products.html','Shop products')}${link('account.html','My account',true)}${link('orders.html','Order history',true)}${link('seller.html','Artisan workspace',true)}${link('admin.html','Admin preview',true)}</div><p class="app-footnote">Coupons, custom commissions and full returns-management workflows are outside V1.</p></aside></div>`}
function render(){({checkout,confirmation,auth,account,orders,order,seller,admin,recommendations,help}[page]||help)();initHeader()}
async function boot(){if(window.FabrixAPI?.ready)await window.FabrixAPI.ready;syncFromAPI();render()}
boot();
window.addEventListener('fabrix:catalog',()=>render());
window.addEventListener('fabrix:hydrated',()=>{syncFromAPI();render()});
})();
