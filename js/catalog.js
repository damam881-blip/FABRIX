'use strict';
// Shared demonstration catalogue for both pages. No remote API or real inventory.
const products = [
  {id:1,name:'Sculpted arch earrings',maker:'Aster Metalworks',price:46,category:'Jewelry',tag:'Low stock',bg:1,stock:3},
  {id:2,name:'Ribbed beeswax candle',maker:'Kindred Flame',price:32,category:'Home objects',tag:'New',bg:2,stock:16},
  {id:3,name:'Hand-knit pebble scarf',maker:'North Loop Knits',price:64,category:'Fiber & textile',tag:'Natural fibers',bg:3,stock:10},
  {id:4,name:'Botanical linen hoop',maker:'Field Note Stitchery',price:52,category:'Fiber & textile',tag:'Made to order',bg:4,stock:8},
  {id:5,name:'Cloudline ceramic vase',maker:'Morrow Clay Studio',price:78,category:'Ceramics',tag:'Bestseller',bg:1,stock:9},
  {id:6,name:'Woven ember wall piece',maker:'Thread & Timber',price:124,category:'Home objects',tag:'One of a kind',bg:2,stock:1}
];

const extras = [
  {id:7,name:'Hand-thrown cup set',maker:'Morrow Clay Studio',price:58,category:'Ceramics',material:'Clay',style:'Minimal',color:'Beige',tag:'New',bg:2,stock:8},
  {id:8,name:'Hammered silver pendant',maker:'Aster Metalworks',price:42,category:'Jewelry',material:'Metal',style:'Modern',color:'Silver',tag:'Small batch',bg:1,stock:4},
  {id:9,name:'Loom-woven cotton runner',maker:'North Loop Knits',price:88,category:'Fiber & textile',material:'Natural fiber',style:'Rustic',color:'Beige',tag:'Natural fibers',bg:3,stock:5},
  {id:10,name:'Carved oak bookend',maker:'Thread & Timber',price:72,category:'Home objects',material:'Wood',style:'Rustic',color:'Brown',tag:'One of a kind',bg:4,stock:1},
  {id:11,name:'Speckled stoneware bowl',maker:'Morrow Clay Studio',price:54,category:'Ceramics',material:'Clay',style:'Minimal',color:'Gray',tag:'Bestseller',bg:1,stock:11},
  {id:12,name:'Soft linen table cloth',maker:'Field Note Stitchery',price:95,category:'Fiber & textile',material:'Natural fiber',style:'Minimal',color:'White',tag:'Made by hand',bg:2,stock:7}
];
products.push(...extras);
