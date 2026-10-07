/* Capture real stored outputs. This script performs only GET requests. */
const fs = require('node:fs');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.SIGNALBRIEF_PLAYWRIGHT_PATH || 'playwright');
const base = process.env.SIGNALBRIEF_TEST_URL || 'http://127.0.0.1:8009';
const run = 'd1434228a9ad4f92acc120d45af1c437';
(async()=>{
  const browser = await chromium.launch({headless:true,
    executablePath:process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const page = await browser.newPage({viewport:{width:1600,height:1050}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  fs.mkdirSync('docs/assets',{recursive:true});
  try {
    await page.goto(base+'/showcase?run='+run);
    await page.locator('.detail-header h2').waitFor();
    assert.equal(await page.locator('.detail-header .badge').textContent(),'Approved');
    await page.screenshot({path:'docs/assets/verified-workspace.png'});
    await page.getByRole('button',{name:'Evidence',exact:true}).click();
    await page.locator('.detail-body details').first().evaluate(n=>n.open=true);
    await page.locator('#detail').screenshot({path:'docs/assets/frozen-evidence.png'});
    await page.getByRole('button',{name:'Agent record',exact:true}).click();
    const records=page.locator('.detail-body details');
    assert.equal(await records.count(),5);
    const crew=records.filter({has:page.locator('summary', {hasText:'CrewAI'})});
    await crew.first().evaluate(n=>n.open=true);
    await page.locator('#detail').screenshot({path:'docs/assets/crewai-execution.png'});
    await crew.first().evaluate(n=>n.open=false);
    const critic=records.filter({has:page.locator('summary',{hasText:/critic/i})});
    assert.equal(await critic.count(),1);
    await critic.first().evaluate(n=>n.open=true);
    await page.locator('#detail').screenshot({path:'docs/assets/autogen-critique.png'});
    await page.getByRole('button',{name:'Activity & delivery',exact:true}).click();
    await page.locator('#detail').screenshot({path:'docs/assets/approval-delivery.png'});
    await page.getByRole('button',{name:'Strategy brief',exact:true}).click();
    await page.setViewportSize({width:390,height:844});
    await page.locator('.detail-header').scrollIntoViewIfNeeded();
    await page.screenshot({path:'docs/assets/verified-mobile.png'});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    assert.deepEqual(errors,[]);
    fs.writeFileSync('data/proof-capture.json',JSON.stringify({url:base,run_id:run,
      actual_records:5,javascript_errors:errors,mutations:false},null,2));
    console.log('Real run screenshots captured; five agent outputs; no mutations or JavaScript errors.');
  } finally {await browser.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
