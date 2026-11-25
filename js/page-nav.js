"use strict";
// On earlier pages, use dedicated full pages for saved collection and multi-seller bag.
for(const [id,target] of [['favorites-nav','favorites.html'],['cart-nav','cart.html']]){const control=document.getElementById(id);if(control)control.addEventListener('click',event=>{event.preventDefault();event.stopImmediatePropagation();location.href=target;},true);}
