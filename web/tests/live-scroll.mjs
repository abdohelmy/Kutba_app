import {webkit} from "playwright";
import assert from "node:assert/strict";

const browser=await webkit.launch({headless:true});
try {
 for(const viewport of [{width:390,height:844},{width:1024,height:1366}]) {
  const page=await browser.newPage({viewport,isMobile:true,hasTouch:true,serviceWorkers:"block"});
  const errors=[];page.on("pageerror",error=>errors.push(error.message));
  await page.addInitScript(()=>{
   window.scrollFrames=[];
   const original=window.scrollTo.bind(window);
   window.scrollTo=(...args)=>{window.scrollFrames.push(typeof args[0]==="object"?args[0].top:args[1]);original(...args);};
  });
  const segments=Array.from({length:16},(_,i)=>({id:`seg${i}`,ordinal:i,arabic_text:"نص للاختبار",
   translated_text:`Passage ${i}. `+"Care for your neighbours and speak with kindness. ".repeat(8),citations:[],glossary_terms:[]}));
  const sermon={id:"scroll-test",mosque_id:"m1",title:"Reading together",status:"PUBLISHED",target_language:"en",khutba_date:"2026-10-09",segments};
  const highlight=(i,start=0)=>({segment_id:`seg${i}`,start,end:start+10,excerpt:segments[i].translated_text.slice(start,start+10)});
  const state={active:true,status:"matched",session_id:"live-scroll",sequence:0,highlights:[highlight(5)]};
  await page.route("**/api/**",route=>{
   const url=new URL(route.request().url());
   return route.fulfill({json:url.pathname.endsWith("/live")?state:url.pathname.endsWith("/scroll-test")?sermon:{}});
  });
  await page.goto("http://127.0.0.1:3000/#read/scroll-test");
  await page.getByRole("button",{name:"Follow imam",exact:true}).click();
  await page.waitForTimeout(1100);
  const first=await page.locator("[data-live-highlight='true']").first().boundingBox();
  assert.ok(first.y>=viewport.height*.18&&first.y<viewport.height*.5,JSON.stringify(first));
  assert.ok(await page.evaluate(()=>window.scrollFrames.length)>5,"Movement should be animated");
  const settled=await page.evaluate(()=>scrollY);
  state.highlights=[highlight(5,11)];state.sequence++;
  await page.waitForTimeout(1600);
  assert.ok(Math.abs(await page.evaluate(()=>scrollY)-settled)<3,"Visible next text must not recenter the page");

  await page.evaluate(()=>window.dispatchEvent(new Event("touchmove")));
  await page.getByRole("button",{name:"Return to live",exact:true}).waitFor();
  state.highlights=[highlight(8)];state.sequence++;
  await page.waitForTimeout(1600);
  assert.ok(Math.abs(await page.evaluate(()=>scrollY)-settled)<3,"Manual scroll pause must hold");
  const controls=await page.locator(".live-follow-bar").boundingBox();
  assert.ok(controls.y>0&&controls.y+controls.height<=viewport.height,"Return control must remain visible");
  await page.getByRole("button",{name:"Return to live",exact:true}).click();
  await page.waitForTimeout(1000);
  assert.ok(await page.evaluate(()=>scrollY)>settled);
  await page.keyboard.press("PageUp");
  await page.getByRole("button",{name:"Return to live",exact:true}).waitFor();
  await page.emulateMedia({reducedMotion:"reduce"});
  state.highlights=[highlight(10)];state.sequence++;
  await page.waitForTimeout(1200);
  await page.evaluate(()=>window.scrollFrames=[]);
  await page.getByRole("button",{name:"Return to live",exact:true}).click();
  await page.waitForTimeout(250);
  assert.equal(await page.evaluate(()=>window.scrollFrames.length),1,"Reduced motion must move without animation");
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(errors,[]);
  console.log(`Live scrolling passed (${viewport.width}px): smooth movement, stable reading band, touch/keyboard pause, visible return control, reduced motion`);
  await page.close();
 }
} finally {await browser.close();}
