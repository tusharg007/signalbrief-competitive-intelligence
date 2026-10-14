/* Record readable evidence boards and additional real operator controls for final editing. */
'use strict';
const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');
const {chromium}=require(process.env.SIGNALBRIEF_PLAYWRIGHT_PATH||'playwright');
const root=path.resolve(__dirname,'..'),work=path.join(root,'data/walkthrough'),base='http://127.0.0.1:8013';
const source=fs.readFileSync(path.join(root,'scripts/record_walkthrough.cjs'),'utf8');
fs.writeFileSync(path.join(root,'signalbrief/static/walkthrough-only.css'),source.match(/<style>([\s\S]*?)<\/style>/)[1].replace('max-height:690px','max-height:550px'));
const report=JSON.parse(fs.readFileSync(path.join(work,'recording-report.json'),'utf8'));
const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pause=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const context=await browser.newContext({viewport:{width:1600,height:900},recordVideo:{dir:work,size:{width:1600,height:900}}});
 const page=await context.newPage(),start=Date.now(),chapters=[],boards=[];const seconds=()=>Number(((Date.now()-start)/1000).toFixed(3));
 async function board(title,caption,body,hold=11000){
  fs.writeFileSync(path.join(work,'proof.html'),`<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/static/walkthrough-only.css"></head><body><div class="tag">SIGNALBRIEF / WALKTHROUGH EVIDENCE</div><h1>${escape(title)}</h1><p class="muted">${escape(caption)}</p>${body}</body></html>`);
  const at=seconds();chapters.push({start:at,title,caption});console.log(title);
  await page.goto(base+'/walkthrough-proof');await pause(hold);
  assert.equal(await page.locator('body').evaluate(el=>getComputedStyle(el).fontSize),'19px');
  await page.screenshot({path:path.join(work,`board-${boards.length+1}.png`)});
  boards.push({title,start:at,end:seconds(),inspect:seconds()-hold/2000});
 }
 await board('SignalBrief: from announcement to a reviewed decision','Real application footage, source evidence, model outputs and human review.',
  '<div class="card"><h2>Detailed feature walkthrough</h2><p>Evidence collection → CrewAI researcher and verifier → AutoGen strategist, critic and editor → version-bound human decision → durable delivery record.</p><p>Fresh Notion tests, adversarial input, revision feedback, approval and rejection, failed-source retry and cancellation, exports and mobile views.</p></div><div class="card"><b>Recording context</b><p>Isolated local workspace, real Groq inference, 4,000-character source cap for fresh runs. Historical Linear and Slack evidence are labelled. No new Slack messages are sent.</p></div>');
 await board('How the system works','The backend owns state and approval authority; the agent frameworks have separate bounded roles.',
  '<div class="card flow">RSS / manual input → authenticated FastAPI ingress<br>→ durable queue → allowlisted HTTPS source collection<br>→ CrewAI research + verification → AutoGen strategy + critique + synthesis<br>→ human decision → transactional outbox → Zapier → Slack</div><div class="grid"><div class="card"><b>Persistence</b><p>Neon PostgreSQL for hosted state; SQLite for this isolated recording.</p></div><div class="card"><b>Recovery</b><p>Leases, heartbeats, checkpoints, stable delivery IDs and bounded retries.</p></div></div>');
 await board('Actual ingress and access checks','Actual HTTP responses from the running app; model outputs are not mocked.',
  '<div class="card"><table><tr><th>Test</th><th>HTTP</th><th>Observed result</th></tr>'+report.tests.map(x=>`<tr><td>${escape(x.label)}</td><td class="pass">${x.status}</td><td>${escape(x.response.detail||x.response.status||'Validated')}</td></tr>`).join('')+'</table></div><p>Identical events reuse the saved run. Conflicting payloads, unauthorized mutation and unregistered sources are rejected.</p>',14000);
 for(const [title,asset,caption] of [
  ['Zapier RSS ingestion — historical published configuration','zapier-rss-live.png','Operator capture from 8 October. The pictured ngrok endpoint is historical; the later cutover used Render.'],
  ['Slack review request — actual historical delivery','slack-review.png','The retained Linear run arrived in Slack for human review. No new Slack message is sent by this recording.'],
  ['Slack approved report — actual historical delivery','slack-approved.png','Separate Slack evidence confirms the approved summary reached its destination, beyond an HTTP webhook receipt.']])
  await board(title,caption,`<img src="/walkthrough-asset/${asset}">`,12000);
 const exported=fs.readFileSync(path.join(work,'exported-brief.md'),'utf8');
 await board('Export the reviewed brief','Actual Markdown returned by the authenticated export endpoint; the complete export includes evidence and execution records.',
  '<div class="card"><pre>'+escape(exported.slice(0,1100))+'</pre></div>',11000);
 await board('Verification and honest limits','49 regression tests passed. Fresh inference and regression fixtures are distinguished.',
  '<div class="grid"><div class="card"><h2>Demonstrated</h2><p>Real source collection and model inference<br>Evidence-linked findings and agent records<br>Feedback-driven revision and report history<br>Human approval; labelled replay for rejection<br>Exports, retry/cancel and access boundaries</p></div><div class="card"><h2>Limits retained</h2><p>Initial quote validation failure is visible<br>Provider retries are retained in the audit<br>Adversarial case failed: no safety conclusion<br>No accuracy, revenue or savings claim<br>Historical Slack proof; fresh delivery disabled</p></div></div><div class="card"><pre>49 passed / 1 dependency deprecation warning\nHosted HTTP requests returned 502 or timed out during preflight.\nLinear HTTPS collection failed certificate verification; it was not bypassed.</pre></div>',14000);
 const credentials=JSON.parse(fs.readFileSync(path.join(work,'operator.json'),'utf8'));
 const session=await context.request.get(base+'/api/session'),csrf=(await session.json()).csrf;
 const login=await context.request.post(base+'/api/login',{headers:{'X-CSRF-Token':csrf},data:{password:credentials.admin_password}});assert.equal(login.status(),200);
 const primary=report.scenarios.find(x=>x.revision);assert(primary);
 await page.goto(base+'/?run='+primary.run_id);await page.locator('.detail-header h2').waitFor();
 await page.getByRole('button',{name:'Activity & delivery',exact:true}).click();await page.locator('.detail-body').scrollIntoViewIfNeeded();
 let at=seconds();chapters.push({start:at,title:'Retry delivery without configuration',caption:'A real retry requeues delivery. With the demo hook deliberately absent, it stays blocked; no Slack message is sent.'});
 await pause(5000);const retry=page.getByRole('button',{name:'Retry delivery',exact:true});assert(await retry.count());await retry.first().click();await pause(8000);
 boards.push({title:'Retry delivery without configuration',start:at,end:seconds(),inspect:seconds()-4});
 const replay=JSON.parse(fs.readFileSync(path.join(work,'rejection-replay.json'),'utf8'));
 await page.goto(base+'/?run='+replay.run_id);await page.locator('#review-feedback').waitFor();
 await page.locator('.review-bar').scrollIntoViewIfNeeded();
 at=seconds();chapters.push({start:at,title:'Reject a labelled replay brief',caption:'Control-only replay of the already generated Notion report, not new inference. This demonstrates the actual rejection API and audit.'});
 await page.locator('#review-feedback').fill('Rejection control exercise: retained output is not approved for delivery.');await pause(5000);
 const rejected=page.waitForResponse(r=>r.url().endsWith('/review')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Reject brief',exact:true}).click();assert.equal((await rejected).status(),200);await pause(7500);
 await page.getByRole('button',{name:'Activity & delivery',exact:true}).click();await page.locator('.detail-body').scrollIntoViewIfNeeded();await pause(7500);
 boards.push({title:'Reject a labelled replay brief',start:at,end:seconds(),inspect:seconds()-4});
 at=seconds();chapters.push({start:at,title:'Operator sign-out',caption:'The real session is cleared. A public showcase visitor has no operator submission or approval authority.'});
 await page.locator('#logout').click();await page.locator('#login').waitFor({state:'visible'});await pause(8500);
 boards.push({title:'Operator sign-out',start:at,end:seconds(),inspect:seconds()-4});
 const video=page.video();await context.close();await video.saveAs(path.join(work,'boards.webm'));await browser.close();
 fs.writeFileSync(path.join(work,'boards-report.json'),JSON.stringify({source:'boards.webm',width:1600,height:900,chapters,boards,end:seconds()},null,2));
 console.log('Readable evidence boards and real operator control clips complete.');
})().catch(e=>{console.error(e.message);process.exitCode=1;});
