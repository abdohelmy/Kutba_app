import {chromium,webkit} from "playwright";
import assert from "node:assert/strict";
import {mkdir} from "node:fs/promises";
const browser=process.env.TEST_BROWSER==="webkit"?await webkit.launch({headless:true}):await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{channel:"chrome"})});
const origin=process.env.TEST_URL||"http://127.0.0.1:3000";
let activePage;
const mosque={id:"m1",name:"Test mosque",city:"Copenhagen",country:"DK"};
const text="Remember Allah with God-consciousness (التقوى). This is a quotation.";
const start=Array.from(text.slice(0,text.indexOf("التقوى"))).length;
const excerpt="This is a quotation.";
const sermon={id:"s1",mosque_id:"m1",title:"A test khutba",khutba_date:"2026-10-02",status:"REVIEW_REQUIRED",segments:[{id:"seg1",ordinal:0,arabic_text:"نص عربي للاختبار فقط",translated_text:text,verification_status:"PASSED",issues:[],citations:[{chunk_id:"c1",source_id:"source1",title:"Source reference",display_reference:"Source reference",authority:"Test source",excerpt,arabic_excerpt:"نص الاقتباس",transliteration:"Example transliteration",url:"https://sunnah.com/",anchor_valid:true,translation_start:Array.from(text).length-Array.from(excerpt).length,translation_end:Array.from(text).length}],glossary_terms:[{arabic_term:"التقوى",display_term:"التقوى",english_phrase:"God-consciousness",literal_translation:"God-consciousness",meaning:"Being mindful of Allah in one’s choices.",transliteration:"al-taqwā",translation_start:start,translation_end:start+Array.from("التقوى").length}]}]};
await mkdir("output/qa",{recursive:true});
try{for(const [name,viewport] of [["iphone",{width:390,height:844}],["ipad",{width:1024,height:1366}]]){
 const context=await browser.newContext({viewport,isMobile:true,hasTouch:true,deviceScaleFactor:2,serviceWorkers:"block"});const page=await context.newPage();activePage=page;const errors=[];page.on("pageerror",e=>{errors.push(e.message);console.error(e.message);});let item=structuredClone(sermon);const mutations=[];
 await page.route("**/api/**",async route=>{const request=route.request(),path=new URL(request.url()).pathname.replace("/api/","");const method=request.method();let data;
 if(method!=="GET")mutations.push(path);
 if(path==="auth/me")data={id:"u1",role:"MOSQUE_ADMIN",mosque_id:"m1"};
 else if(path==="auth/login"||path==="auth/logout")data={status:"ok"};
 else if(path==="reader/mosques")data=[mosque];
 else if(path==="reader/mosques/m1/sermons")data=[item];
 else if(path==="reader/sermons/s1"||path==="admin/sermons/s1/preview")data=item;
 else if(path==="admin/sermons"&&method==="GET")data=[item];
 else if(path==="admin/sermons/s1"&&method==="GET")data=item;
 else if(path==="admin/sermons/s1/segments/seg1"){const body=request.postDataJSON();item.segments[0]={...item.segments[0],...body,verification_status:body.approved?"HUMAN_APPROVED":"PASSED"};data=item.segments[0];}
 else if(path==="admin/sermons/s1/publish"){item.status="PUBLISHED";data={id:"s1",status:"PUBLISHED"};}
 else if(path==="admin/sermons/s1/glossary-candidates")data=[];
 else if(path==="admin/sermons/s1/translate"){item.status="TRANSLATING";data={id:"s1",status:"TRANSLATING"};}
 else if(path==="admin/profile")data=mosque;
 else if(path==="admin/glossary")data=[];
 else return route.fulfill({status:500,json:{detail:"Unexpected test request: "+method+" "+path}});
 return route.fulfill({json:data});});
 await page.goto(origin);await page.getByRole("button",{name:/Read a khutba/}).click();await page.getByRole("button",{name:/Test mosque/}).click();await page.getByRole("button",{name:/A test khutba/}).click();await page.getByRole("button",{name:"التقوى",exact:true}).click();await page.getByRole("dialog").waitFor();assert.equal(await page.getByRole("heading",{name:"God-consciousness"}).count(),1);assert.equal(await page.getByText("al-taqwā",{exact:true}).count(),1);await page.screenshot({path:`output/qa/${name}-glossary.png`});await page.keyboard.press("Escape");await page.getByRole("button",{name:"Source: Source reference",exact:true}).click();assert.equal(await page.getByRole("link",{name:"Open source"}).getAttribute("href"),"https://sunnah.com/");await page.keyboard.press("Escape");
 assert.equal(await page.locator("article").getByText("نص عربي للاختبار فقط").count(),0);await page.getByRole("button",{name:"Save for offline",exact:true}).click();assert.equal(await page.getByRole("button",{name:"Remove saved copy"}).count(),1);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await page.screenshot({path:`output/qa/${name}-reader.png`,fullPage:true});
 await page.goto(origin+"/#saved");await page.getByRole("button",{name:/A test khutba/}).click();await page.getByText(/Saved copy/).waitFor();
 await page.goto(origin+"/#review/s1");await page.getByRole("button",{name:"Save & approve passage"}).click();await page.getByRole("button",{name:"Publish khutba",exact:true}).click();await page.getByRole("alertdialog").getByRole("button",{name:"Publish",exact:true}).click();await page.getByRole("heading",{name:"Add word meanings"}).waitFor();assert(mutations.includes("admin/sermons/s1/publish"));
 item.status="FAILED";await page.goto(origin+"/#review/s1");await page.getByRole("button",{name:"Create grounded translation"}).click();await page.getByRole("heading",{name:"Translating your khutba"}).waitFor();assert(!mutations.some(p=>p.endsWith("/source-text")));
 await page.goto(origin+"/#settings");await page.getByRole("heading",{name:"Add a mosque glossary term"}).waitFor();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await page.screenshot({path:`output/qa/${name}-admin.png`,fullPage:true});
 await page.goto(origin);await page.locator('main[data-ready="true"]').waitFor();await page.screenshot({path:`output/qa/${name}-start.png`,fullPage:true});assert.deepEqual(errors,[]);console.log(`${process.env.TEST_BROWSER||"chromium"} ${name}: reader, glossary, source, saved copy, review/publish, retry and layout passed`);await context.close();
}}catch(error){if(activePage&&!activePage.isClosed()){console.error(await activePage.locator("body").innerText());await activePage.screenshot({path:"output/qa/failure.png",fullPage:true});}throw error;}finally{await browser.close();}
