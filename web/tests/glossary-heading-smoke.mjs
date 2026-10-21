import {webkit} from 'playwright';
import assert from 'node:assert/strict';
const browser=await webkit.launch({headless:true});
try {
  for(const width of [390,1024]) for(const language of ['en','da']) {
    const page=await browser.newPage({viewport:{width,height:1000},isMobile:true,hasTouch:true,serviceWorkers:'block'});
    const text=language==='da'?'🌙 Vær gudsbevidst (التقوى).':'🌙 Cultivate mindful devotion (التقوى).';
    const index=Array.from(text).indexOf('ا');
    const term={arabic_term:'التقوى',display_term:'التقوى',meaning:'Mindfulness of Allah',literal_translation:'piety',english_phrase:'God-consciousness',localized_phrase:'God-consciousness',popup_phrase:'piety',popup_language:'en',translation_start:index,translation_end:index+6};
    const sermon={id:'s',mosque_id:'m',title:'Test khutba',target_language:language,khutba_date:'2026-10-02',status:'PUBLISHED',segments:[{id:'seg',ordinal:0,translated_text:text,citations:[],glossary_terms:[term]}]};
    await page.route('**/api/**',route=>route.fulfill({json:sermon}));
    await page.goto('http://127.0.0.1:3000/#read/s');
    await page.getByRole('button',{name:'التقوى',exact:true}).click();
    const dialog=page.getByRole('dialog');
    await dialog.getByRole('heading',{name:language==='da'?'🌙 Vær gudsbevidst':'🌙 Cultivate mindful devotion',exact:true}).waitFor();
    assert.equal(await dialog.getByRole('heading',{name:'God-consciousness',exact:true}).count(),0);
    assert.equal(await dialog.getByRole('heading',{name:'piety',exact:true}).count(),0);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    console.log(`Popup uses selected ${language} wording (${width}px)`);
    await page.close();
  }
}finally{await browser.close();}
