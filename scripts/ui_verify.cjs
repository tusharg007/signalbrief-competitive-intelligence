/* Exercise the actual local dashboard. Never approve, reject, or deliver a real report. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.SIGNALBRIEF_PLAYWRIGHT_PATH || 'playwright');
const base = process.env.SIGNALBRIEF_TEST_URL || 'http://127.0.0.1:8008';
const env = fs.readFileSync('.env','utf8');
const passwordLine = env.split(/\r?\n/).find(line=>line.startsWith('ADMIN_PASSWORD='));
if (!passwordLine) throw new Error('Configure local ADMIN_PASSWORD');
const password = passwordLine.slice('ADMIN_PASSWORD='.length).replace(/^['"]|['"]$/g,'');
const executablePath = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(file=>fs.existsSync(file));
(async()=>{
  const browser=await chromium.launch({headless:true,...(executablePath?{executablePath}:{})});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  fs.mkdirSync('docs/assets',{recursive:true});
  try {
    await page.goto(base);await page.locator('#login').waitFor({state:'visible'});
    await page.screenshot({path:'docs/assets/login.png',fullPage:true});
    await page.locator('#password').fill(password);
    await page.locator('#login-form button').click();
    await page.locator('#workspace').waitFor({state:'visible'});
    await page.locator('#configuration').waitFor({state:'visible'}).catch(()=>{});
    await page.screenshot({path:'docs/assets/inbox.png',fullPage:true});
    await page.locator('#new-signal').click();await page.locator('#event-dialog').waitFor({state:'visible'});
    assert(await page.locator('#competitor option').count() >= 1);
    await page.locator('#close-dialog').click();
    const cards=page.locator('.run-card');
    if(await cards.count()){
      const ready=cards.filter({has:page.locator('.badge.awaiting_approval')});
      await (await ready.count()?ready.first():cards.first()).click();
      await page.locator('.detail-header h2').waitFor({state:'visible'});
      await page.screenshot({path:'docs/assets/brief.png',fullPage:true});
      await page.screenshot({path:'docs/assets/workspace.png'});
      for(const title of ['Evidence','Agent record','Activity & delivery']){
        await page.getByRole('button',{name:title,exact:true}).click();
        assert((await page.locator('.detail-body').textContent()).length>30);
      }
      await page.getByRole('button',{name:'Agent record',exact:true}).click();
      await page.screenshot({path:'docs/assets/agents.png',fullPage:true});
      await page.getByRole('button',{name:'Strategy brief',exact:true}).click();
    }
    await page.setViewportSize({width:390,height:844});
    if(await cards.count())await page.locator('#detail').scrollIntoViewIfNeeded();
    await page.screenshot({path:'docs/assets/mobile.png'});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile layout overflows');
    assert.deepEqual(errors,[],'Browser console errors');
    await page.locator('#logout').click();await page.locator('#login').waitFor({state:'visible'});
    const result={url:base,login:'passed',tabs:'passed',new_signal_dialog:'passed',mobile:'passed',
      javascript_errors:errors,screenshots:['login','inbox','workspace','brief','agents','mobile'],
      real_report_modified:false};
    fs.writeFileSync('data/ui-verification.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
  } finally { await browser.close(); }
})().catch(error=>{console.error(error.message);process.exitCode=1;});
