import {webkit} from "playwright";
import assert from "node:assert/strict";

const browser=await webkit.launch({headless:true});
try{
 for(const viewport of [{width:390,height:844},{width:1024,height:1366}]){
  const page=await browser.newPage({viewport,isMobile:true,hasTouch:true,serviceWorkers:"block"});
  const errors=[];page.on("pageerror",error=>errors.push(error.message));
  await page.addInitScript(()=>{
   let stopped=0;
   window.audioUploads=[];
   const originalFetch=window.fetch.bind(window);
   window.fetch=async(input,init)=>{
    if(init?.body instanceof FormData&&String(input).includes("/live/audio?")){
     const view=new DataView(await init.body.get("file").arrayBuffer());
     window.audioUploads.push({kind:new URL(String(input),location.href).searchParams.get("kind"),bytes:view.getUint32(40,true),first:view.getInt16(44,true),last:view.getInt16(view.byteLength-2,true)});
    }
    return originalFetch(input,init);
   };
   Object.defineProperty(navigator,"mediaDevices",{configurable:true,value:{getUserMedia:async()=>({getTracks:()=>[{stop:()=>stopped++,addEventListener:()=>{}}]})}});
   class FakeContext{state="running";sampleRate=16000;destination={};audioWorklet={addModule:async()=>{}};resume=async()=>{};close=async()=>{this.state="closed";};createMediaStreamSource=()=>({connect:()=>{}});createGain=()=>({gain:{value:0},connect:()=>{}});}
   class FakeWorklet{port={};connect(){}disconnect(){}constructor(){Object.defineProperty(this.port,"onmessage",{set:fn=>{window.microphoneLevel=rms=>fn({data:{type:"level",rms}});window.microphoneChunk=value=>fn({data:new Float32Array(32000).fill(value)});setTimeout(()=>fn({data:{type:"level",rms:0.04}}),100);setTimeout(()=>window.microphoneChunk(0.1),500);}});}}
   Object.defineProperty(window,"AudioContext",{configurable:true,value:FakeContext});Object.defineProperty(window,"AudioWorkletNode",{configurable:true,value:FakeWorklet});
   Object.defineProperty(navigator,"wakeLock",{configurable:true,value:{request:async()=>({release:async()=>{}})}});
   window.microphoneStopped=()=>stopped;
  });
  const text="🌙 Seek truth. Keep knowledge (العلم) close.";
  const first="Seek truth.",start=text.indexOf(first),end=start+first.length;
  const sermon={id:"s1",mosque_id:"m1",title:"Live khutba",khutba_date:"2026-10-09",target_language:"en",status:"PUBLISHED",segments:[{id:"seg",ordinal:0,arabic_text:"نص عربي للاختبار",translated_text:text,verification_status:"HUMAN_APPROVED",issues:[],citations:[{chunk_id:"c1",source_id:"quran.com:2:152",title:"Al-Baqarah",display_reference:"Al-Baqarah 2:152",authority:"Quran.com",excerpt:first,arabic_excerpt:"فاذكروني",url:"https://quran.com/2/152",translation_start:2,translation_end:2+first.length}],glossary_terms:[]}]};
  const state={active:false,status:"idle",session_id:"live1",sequence:-1,audio_sequence:-1,worker_ready:true,mapping_ready:false,preparing:false,highlights:[]};
  let uploads=0,prepares=0;
  await page.route("**/api/**",async route=>{
   const req=route.request(),url=new URL(req.url()),path=url.pathname.replace("/api/","");let data;
   if(path==="auth/me")data={role:"MOSQUE_ADMIN"};
   else if(path==="admin/sermons/s1"||path==="reader/sermons/s1")data=sermon;
   else if(path==="admin/sermons/s1/live/prepare"){prepares++;state.mapping_ready=true;data={status:"preparing"};}
   else if(path==="admin/sermons/s1/live"){
    if(req.method()==="POST"){const body=req.postDataJSON();state.active=body.action!=="stop";state.status=body.action==="pause"?"paused":"waiting";}
    else if(!state.mapping_ready){state.preparing=true;setTimeout(()=>{state.mapping_ready=true;state.preparing=false;},100);}
    data={...state};
   }else if(path==="admin/sermons/s1/live/audio"){
    const sequence=Number(url.searchParams.get("sequence"));assert.ok(sequence>state.audio_sequence);state.audio_sequence=sequence;uploads++;data={status:"queued"};
   }else if(path==="reader/sermons/s1/live")data={...state};
   else return route.fulfill({status:404,json:{detail:"Unexpected request: "+path}});
   return route.fulfill({json:data});
  });
  await page.goto("http://127.0.0.1:3000/#review/s1");
  assert.equal(await page.getByRole("button",{name:"Prepare live passages",exact:true}).count(),0);
  await page.getByRole("button",{name:"Start microphone",exact:true}).waitFor();
  await page.waitForFunction(()=>Array.from(document.querySelectorAll("button")).some(b=>b.textContent==="Start microphone"&&!b.disabled));
  assert.equal(prepares,0); // Preparation is server-driven, not an extra admin step.
  await page.getByRole("button",{name:"Start microphone",exact:true}).click();
  await page.getByRole("button",{name:"Pause microphone",exact:true}).waitFor().catch(async error=>{console.error(await page.locator("body").innerText());throw error;});
  await page.waitForFunction(()=>true);await page.waitForTimeout(750);assert.equal(uploads,1);
  await page.getByText("Sound detected",{exact:true}).waitFor();
  assert.ok(Number(await page.getByRole("meter",{name:"Microphone input level"}).getAttribute("value"))>0);
  await page.evaluate(()=>window.microphoneLevel(0));
  await page.waitForTimeout(1600);await page.evaluate(()=>window.microphoneLevel(0));
  await page.getByText("No sound detected",{exact:true}).waitFor();
  assert.equal(await page.getByRole("meter",{name:"Microphone input level"}).getAttribute("value"),"0");
  assert.equal(uploads,1); // Level telemetry must never be uploaded as audio.
  await page.evaluate(()=>window.microphoneChunk(0.2));
  await page.waitForTimeout(200);
  await page.evaluate(()=>window.microphoneChunk(0.3));
  await page.waitForTimeout(200);
  await page.evaluate(()=>window.microphoneChunk(0.4));
  await page.waitForTimeout(200);
  await page.evaluate(()=>window.microphoneChunk(0.5));
  await page.waitForTimeout(200);
  const audioUploads=await page.evaluate(()=>window.audioUploads);
  assert.deepEqual(audioUploads.map(x=>[x.kind,x.bytes]),[["quick",64000],["quick",128000],["quick",128000],["full",256000],["quick",128000]]);
  assert.equal(audioUploads[3].first,Math.round(0.1*32767));
  assert.equal(audioUploads[3].last,Math.round(0.4*32767));
  assert.equal(audioUploads[4].first,Math.round(0.4*32767));
  assert.equal(audioUploads[4].last,Math.round(0.5*32767));
  await page.evaluate(()=>window.microphoneLevel(0.06));
  await page.getByText("Sound detected",{exact:true}).waitFor();
  await page.getByRole("button",{name:"Pause microphone",exact:true}).click();
  assert.equal(await page.getByRole("meter",{name:"Microphone input level"}).count(),0);
  await page.getByRole("button",{name:"Resume microphone",exact:true}).click();
  await page.waitForTimeout(750);assert.equal(uploads,6);
  await page.getByRole("button",{name:"End live session",exact:true}).click();
  await page.getByRole("button",{name:"Start microphone",exact:true}).waitFor();
  assert.ok(await page.evaluate(()=>window.microphoneStopped())>=2);
  state.active=true;state.status="waiting";state.provisional=true;state.highlights=[{segment_id:"seg",start,end,excerpt:first}];
  await page.goto("http://127.0.0.1:3000/#read/s1");
  await page.getByRole("button",{name:"Follow imam",exact:true}).click();
  await page.locator(".live-highlight").first().waitFor();
  assert.equal(await page.locator(".live-highlight").first().innerText(),first);
  await page.getByText("Finding position",{exact:true}).waitFor();
  state.provisional=false;state.status="matched";
  await page.getByRole("button",{name:"Source: Al-Baqarah 2:152",exact:true}).click();
  await page.getByRole("dialog").getByText("فاذكروني",{exact:true}).waitFor();
  await page.keyboard.press("Escape");
  state.status="waiting";await page.getByText(/Waiting for a clear match/).waitFor();
  assert.equal(await page.locator(".live-highlight").first().innerText(),first);
  const tentative="Keep knowledge (العلم) close.";
  state.tentative_highlights=[{segment_id:"seg",start:text.indexOf(tentative),end:text.length,excerpt:tentative,basis:"timer"}];
  await page.locator(".live-highlight-tentative").first().waitFor();
  await page.locator(".live-highlight-estimated").first().waitFor();
  state.tentative_highlights[0].basis="words";
  await page.waitForFunction(()=>document.querySelector(".live-highlight-tentative")&&!document.querySelector(".live-highlight-estimated"));
  assert.equal(await page.locator(".live-highlight").first().innerText(),first);
  assert.equal(await page.locator(".live-highlight-tentative").first().innerText(),tentative);
  assert.equal(await page.locator(".live-highlight-tentative[data-live-highlight='true']").count(),0);
  await page.getByText(/yellow is tentative/).waitFor();
  state.tentative_highlights=[];
  await page.waitForFunction(()=>!document.querySelector(".live-highlight-tentative"));
  await page.evaluate(()=>window.dispatchEvent(new WheelEvent("wheel")));
  await page.getByRole("button",{name:"Return to live",exact:true}).click();
  const second="Keep knowledge (العلم) close.";state.highlights=[{segment_id:"seg",start:text.indexOf(second),end:text.length,excerpt:second}];state.status="matched";
  await page.waitForFunction(()=>document.querySelector(".live-highlight")?.textContent?.startsWith("Keep knowledge"));
  state.highlights=[{segment_id:"seg",start:0,end:10,excerpt:"stale text"}];
  await page.waitForFunction(()=>!document.querySelector(".live-highlight"));
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(errors,[]);
  console.log(`Live workflow passed (${viewport.width}px): microphone level/silence, automatic preparation, capture, pause/resume, follow, citations, uncertainty, stale-text protection`);
  await page.close();
 }
}finally{await browser.close();}
