import {webkit} from "playwright";
import assert from "node:assert/strict";
const browser = await webkit.launch({headless:true});
try {
  for (const viewport of [{width:390,height:844},{width:1024,height:1366}]) {
    const page = await browser.newPage({viewport,isMobile:true,hasTouch:true,serviceWorkers:"block"});
    const errors=[];
    page.on("pageerror", e=>errors.push(e.message));
    const english={id:"english",mosque_id:"m1",title:"English sermon",khutba_date:"2026-10-02",target_language:"en",status:"PUBLISHED"};
    const text="Vær gudsbevidst (التقوى).";
    const term={arabic_term:"التقوى",display_term:"التقوى",english_phrase:"God-consciousness",localized_phrase:"gudsbevidst",literal_translation:"God-consciousness",meaning:"At være bevidst om Allah.",transliteration:"al-taqwā",translation_start:text.indexOf("التقوى"),translation_end:text.indexOf("التقوى")+"التقوى".length};
    const danish={...english,id:"danish",english_sermon_id:"english",title:"Dansk prædiken",target_language:"da",status:"REVIEW_REQUIRED",segments:[{id:"seg",ordinal:0,translated_text:text,english_text:"Have God-consciousness (التقوى).",arabic_text:"علينا بالتقوى",verification_status:"PENDING",issues:[],citations:[],localized_glossary:[term],glossary_terms:[term]}]};
    let savedDefinition;
    await page.route("**/api/**", async route=> {
      const req=route.request(), path=new URL(req.url()).pathname.replace("/api/","");
      let data;
      if(path==="auth/me") data={id:"u1",role:"MOSQUE_ADMIN"};
      else if(path==="admin/sermons") data=[english,danish];
      else if(path==="admin/sermons/english/danish") data=danish;
      else if(path==="admin/sermons/danish"||path==="reader/sermons/danish") data=danish;
      else if(path==="admin/sermons/danish/title") {danish.title=req.postDataJSON().title;data=danish;}
      else if(path==="admin/sermons/danish/segments/seg") {
        const body=req.postDataJSON();savedDefinition=body.localized_definitions[0].meaning;
        danish.segments[0].verification_status="HUMAN_APPROVED";
        danish.segments[0].localized_glossary[0].meaning=savedDefinition;
        data=danish.segments[0];
      } else if(path==="admin/sermons/danish/publish") {danish.status="PUBLISHED"; data=danish;}
      else if(path==="reader/mosques") data=[{id:"m1",name:"Test mosque",city:"Copenhagen",country:"DK"}];
      else if(path==="reader/mosques/m1/sermons") data=[english,danish];
      else return route.fulfill({status:500,json:{detail:"Unexpected request: "+path}});
      await route.fulfill({json:data});
    });
    await page.goto("http://127.0.0.1:3000/#admin");
    await page.getByRole("button",{name:"Danish translation",exact:true}).click();
    await page.getByRole("heading",{name:"Approved English"}).waitFor({timeout:10000}).catch(async e=>{console.error(page.url(), await page.locator("body").innerText());throw e;});
    await page.getByRole("textbox",{name:/Danish meaning/}).fill("Bevidsthed om Allah i sine valg.",{timeout:10000}).catch(async e=>{console.error(await page.locator("body").innerText());throw e;});
    await page.getByRole("textbox",{name:"Khutba title",exact:true}).fill("Dansk prædiken — updated");
    await page.getByRole("button",{name:"Save title",exact:true}).click();
    await page.getByText("Title updated.",{exact:true}).waitFor();
    assert.equal(await page.getByRole("textbox",{name:/Danish meaning/}).inputValue(),"Bevidsthed om Allah i sine valg.");
    await page.getByRole("button",{name:"Save & approve passage"}).click();
    await page.getByRole("button",{name:"Publish khutba",exact:true}).click();
    await page.getByRole("alertdialog").getByRole("button",{name:"Publish",exact:true}).click();
    await page.getByRole("heading",{name:"Your khutbas"}).waitFor();
    assert.equal(savedDefinition,"Bevidsthed om Allah i sine valg.");
    await page.goto("http://127.0.0.1:3000/#mosque/m1");
    await page.getByRole("button",{name:"Dansk",exact:true}).click();
    assert.equal(await page.getByRole("button",{name:/English sermon/}).count(),0);
    await page.getByRole("button",{name:/Dansk prædiken/}).click();
    await page.getByRole("button",{name:"التقوى",exact:true}).click();
    await page.getByRole("heading",{name:"gudsbevidst",exact:true}).waitFor();
    assert.equal(await page.getByText("al-taqwā",{exact:true}).count(),1);
    await page.keyboard.press("Escape");
    assert.equal(await page.getByRole("link",{name:"Download PDF"}).getAttribute("href"),"/api/reader/sermons/danish/pdf");
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    assert.deepEqual(errors,[]);
    console.log(`Danish workflow passed (${viewport.width}px): generate, review definitions, publish, filter, popup, PDF link`);
    await page.close();
  }
} finally {await browser.close();}
