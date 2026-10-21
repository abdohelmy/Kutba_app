import {webkit} from "playwright";
import assert from "node:assert/strict";

const browser=await webkit.launch({headless:true});
try {
 for(const viewport of [{width:390,height:844},{width:1024,height:1366}]){
  const page=await browser.newPage({viewport,isMobile:true,hasTouch:true,serviceWorkers:"block"});
  const errors=[];page.on("pageerror",e=>errors.push(e.message));
  const mosque={id:"m1",name:"Test Mosque",city:"Copenhagen",country:"DK",approval_status:"PENDING",is_active:false,admins:[{id:"u1",username:"admin",display_name:"Test Admin",contact_email:"admin@example.com",is_active:true}]};
  const pendingTerm={id:"g1",scope:"global",arabic_term:"كلمةاختبار",literal_translation:"test expression",meaning:"Test definition.",approval_status:"PENDING",submitted_by:"Test Mosque"};
  const calls=[];
  await page.route("**/api/**",async route=>{
   const req=route.request(),path=new URL(req.url()).pathname.replace("/api/","");
   calls.push({path,method:req.method(),body:req.postData()});
   let data;
   if(path==="owner/dashboard")data={username:"abdo",contact_email:"abdo@example.com",email_enabled:false,pending:mosque.approval_status==="PENDING"?1:0,pending_glossary:pendingTerm.approval_status==="PENDING"?1:0,mosques:1,translating:0,failed:0};
   else if(path==="owner/mosques")data=[mosque];
   else if(path==="owner/mosques/m1"){
    const body=req.postDataJSON();if(body.name)mosque.name=body.name;
    if(body.action==="approve"){mosque.approval_status="APPROVED";mosque.is_active=true;}
    if(body.action==="suspend")mosque.is_active=false;
    data={status:"saved"};
   }else if(path==="owner/sermons")data=[];
   else if(path==="owner/audit")data=[];
   else if(path==="owner/glossary")data=req.method()==="GET"?{global:[pendingTerm],mosque:[]}:{status:"saved"};
   else if(path==="owner/glossary/global/g1"){pendingTerm.approval_status=req.postDataJSON().action==="approve"?"APPROVED":"REJECTED";data={status:"saved"};}
   else if(path==="auth/me")data={role:"MOSQUE_ADMIN"};
   else if(path==="admin/profile"){if(req.method()==="PATCH")mosque.city=req.postDataJSON().city;data=mosque;}
   else if(path==="admin/glossary")data=[];
   else if(path==="owner/users/u1/reset-link")data={link:"https://example.com/#reset/one-time-token",email_sent:false};
   else if(path==="auth/reset-password"||path==="auth/register-mosque")data={status:"saved"};
   else return route.fulfill({status:500,json:{detail:"Unexpected request: "+path}});
   await route.fulfill({json:data});
  });
  await page.goto("http://127.0.0.1:3000/#owner");
  await page.getByRole("heading",{name:"Manage Khutba",exact:true}).waitFor();
  await page.getByRole("button",{name:"Approve",exact:true}).click();
  await page.getByRole("button",{name:"Suspend",exact:true}).waitFor();
  await page.getByRole("button",{name:"Rename",exact:true}).click();
  await page.getByRole("dialog").getByRole("textbox",{name:"Mosque name"}).fill("New Mosque Name");
  await page.getByRole("button",{name:"Save name"}).click();
  await page.getByRole("heading",{name:"New Mosque Name"}).waitFor();
  await page.getByRole("button",{name:"Password-reset link"}).click();
  await page.getByRole("heading",{name:"One-time password-reset link"}).waitFor();
  assert.match(await page.getByRole("textbox",{name:"Password reset link"}).inputValue(),/#reset/);
  await page.keyboard.press("Escape");
  await page.getByRole("button",{name:"Suspend",exact:true}).click();
  await page.getByRole("alertdialog").getByRole("button",{name:"Cancel",exact:true}).click();
  assert.equal(calls.filter(c=>c.body?.includes('"suspend"')).length,0);
  await page.getByRole("tab",{name:/Glossary/}).click();
  await page.getByRole("button",{name:"Awaiting approval (1)",exact:true}).click();
  await page.getByRole("button",{name:"Approve definition",exact:true}).click();
  await page.getByRole("button",{name:"Awaiting approval (0)",exact:true}).waitFor();
  await page.getByRole("button",{name:"All entries",exact:true}).click();
  await page.getByRole("button",{name:"Add term",exact:true}).click();
  const dialog=page.getByRole("dialog");
  await dialog.getByRole("textbox",{name:"Arabic word or expression"}).fill("التقوى");
  await dialog.getByRole("textbox",{name:"English phrase"}).fill("God-consciousness");
  await dialog.getByRole("textbox",{name:"Explanation"}).fill("Being mindful of Allah.");
  await dialog.getByRole("button",{name:"Save globally"}).click();
  await dialog.waitFor({state:"hidden"});
  assert.ok(calls.some(c=>c.path==="owner/glossary"&&c.method==="PUT"));
  assert.ok(calls.some(c=>c.path==="owner/glossary/global/g1"&&c.method==="PATCH"));
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:`/private/tmp/khutba-owner-${viewport.width}.png`,fullPage:true});
  await page.goto("http://127.0.0.1:3000/#settings");
  await page.getByLabel("City",{exact:true}).fill("Odense");
  await page.getByRole("button",{name:"Save profile",exact:true}).click();
  await page.getByText("Mosque profile updated.",{exact:true}).waitFor();
  assert.equal(mosque.city,"Odense");
  await page.goto("http://127.0.0.1:3000/#reset/"+"a".repeat(43));
  await page.getByRole("textbox",{name:"New password"}).fill("new-password");
  await page.getByRole("button",{name:"Save password"}).click();
  await page.getByRole("heading",{name:"Welcome back"}).waitFor();
  await page.getByRole("button",{name:"Create a mosque profile",exact:true}).click();
  assert.equal(await page.getByRole("textbox",{name:"Permission password"}).count(),0);
  for(const [name,value] of [["Mosque name","Example Mosque"],["City","Copenhagen"],["Your name","New Admin"],["Contact email","admin@example.com"],["Username","new-admin"],["Password","pass123"]])await page.getByLabel(name,{exact:true}).fill(value);
  await page.getByRole("button",{name:"Create profile",exact:true}).click();
  await page.getByText("Request submitted. You can sign in once the app owner approves your mosque.").waitFor();
  assert.equal(calls.filter(c=>c.path==="auth/login").length,0);
  assert.deepEqual(errors,[]);
  console.log(`Owner workflow passed (${viewport.width}px): approval, rename, reset link, confirmation, glossary, setup, pending signup`);
  await page.close();
 }
}finally{await browser.close();}
