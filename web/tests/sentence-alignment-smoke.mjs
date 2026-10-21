import {webkit} from 'playwright';
import assert from 'node:assert/strict';

const browser=await webkit.launch({headless:true});
try {
  for (const width of [390,1024]) for (const language of ['en','da']) {
    const page=await browser.newPage({viewport:{width,height:1000},isMobile:true,hasTouch:true,serviceWorkers:'block'});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    const arabic='الحمد لله. اتقوا الله.';
    const text=language==='en'?'Praise Allah. Have God-consciousness.':'Lovpris Allah. Vær gudsbevidst.';
    const split=text.indexOf(' ' ,text.indexOf('.'))+1;
    const segment={id:'seg',ordinal:0,arabic_text:arabic,translated_text:text,verification_status:'PASSED',issues:[],citations:[]};
    const item={id:'s',mosque_id:'m',title:'Test sermon',khutba_date:'2026-10-02',target_language:language,status:'REVIEW_REQUIRED',segments:[segment]};
    let requests=0;
    await page.route('**/api/**',async route=>{
      const path=new URL(route.request().url()).pathname;
      let data;
      if(path==='/api/auth/me')data={id:'a',role:'MOSQUE_ADMIN'};
      else if(path==='/api/admin/sermons/s')data=item;
      else if(path==='/api/admin/sermons/s/segments/seg/alignment'){
        requests++;
        data=[{translation_start:0,translation_end:split-1,arabic_start:0,arabic_end:10},
          {translation_start:split,translation_end:text.length,arabic_start:11,arabic_end:arabic.length}];
      }else return route.fulfill({status:404,json:{detail:path}});
      return route.fulfill({json:data});
    });
    await page.goto('http://127.0.0.1:3000/#review/s');
    const editor=page.getByRole('textbox',{name:language==='en'?'English translation':'Danish translation',exact:true});
    await editor.focus();
    await page.getByText('Matching Arabic highlighted',{exact:true}).waitFor();
    assert.equal(await page.locator('mark.source-sentence').innerText(),'الحمد لله.');
    await editor.evaluate((el,position)=>{el.setSelectionRange(position,position);el.dispatchEvent(new Event('select',{bubbles:true}));},split+2);
    await page.waitForFunction(()=>document.querySelector('mark.source-sentence')?.textContent==='اتقوا الله.');
    // Insert in the first sentence, then check that the second sentence's mapping moved.
    await editor.evaluate(el=>{el.setSelectionRange(2,2);el.dispatchEvent(new Event('select',{bubbles:true}));});
    await page.keyboard.insertText('very ');
    await editor.evaluate((el,position)=>{el.setSelectionRange(position,position);el.dispatchEvent(new Event('select',{bubbles:true}));},split+7);
    await page.waitForFunction(()=>document.querySelector('mark.source-sentence')?.textContent==='اتقوا الله.');
    assert.equal(requests,1,'Typing must not make repeated model requests');
    // A replacement spanning both sentences must not keep a misleading mapping.
    await editor.fill('A completely rewritten passage.');
    assert.equal(await page.locator('mark.source-sentence').count(),0);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    assert.deepEqual(errors,[]);
    console.log(`Arabic sentence highlighting passed (${language}, ${width}px)`);
    await page.close();
  }
}finally{await browser.close();}
