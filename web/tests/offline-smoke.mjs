import {chromium,webkit} from "playwright";
import assert from "node:assert/strict";
const browser=process.env.TEST_BROWSER==="webkit"?await webkit.launch():await chromium.launch({channel:"chrome"});
try{
 const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
 const page=await context.newPage();const origin=process.env.TEST_URL||"http://127.0.0.1:3001";
 await page.goto(origin);await page.locator('main[data-ready="true"]').waitFor();
 await page.evaluate(async()=>{await navigator.serviceWorker.ready;localStorage.setItem("khutba:saved",JSON.stringify({offline:{id:"offline",mosque_id:"offline-mosque",title:"Offline test khutba",khutba_date:"2026-10-02",status:"PUBLISHED",segments:[{id:"offline-segment",ordinal:0,translated_text:"This is a saved test passage.",citations:[],glossary_terms:[]}]}}));});
 await page.waitForFunction(async()=>{const keys=await caches.keys();const cache=await caches.open(keys.find(k=>k.startsWith("khutba-shell-")));const assets=(await cache.keys()).map(r=>r.url);return assets.some(url=>url.includes("/page-"))&&assets.some(url=>url.endsWith(".css"))&&assets.some(url=>url.includes("/framework-"));});
 console.log("WebMCP native browser support:",await page.evaluate(()=>!!document.modelContext));
 await context.setOffline(true);await page.goto(origin+"/#saved-read/offline");await page.getByRole("heading",{name:"Offline test khutba"}).waitFor();assert.equal(await page.getByText("This is a saved test passage.",{exact:true}).count(),1);assert.equal(await page.getByText(/Saved copy/).count(),1);console.log(`${process.env.TEST_BROWSER||"chromium"}: installed shell + saved reader reopen without network`);
 await context.close();
}finally{await browser.close();}
