/* Capture legible full-context and zoomed views of the original historical proof images. */
'use strict';
const fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.SIGNALBRIEF_PLAYWRIGHT_PATH||'playwright');
const root=path.resolve(__dirname,'..'),work=path.join(root,'data/walkthrough'),base='http://127.0.0.1:8013';
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const escape=s=>String(s).replace(/[&<>]/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[x]));
(async()=>{
 const css=path.join(root,'signalbrief/static/walkthrough-only.css');
 fs.appendFileSync(css,'\n.proof-crop.zoom{width:1460px;height:550px;overflow:hidden;position:relative;margin:auto}.proof-crop.zoom img{position:absolute;max-width:none;max-height:none;width:1920px;left:-500px;top:-240px}.proof-crop.zapier.zoom img{top:-300px}');
 const report=JSON.parse(fs.readFileSync(path.join(work,'boards-report.json'),'utf8'));
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const context=await browser.newContext({viewport:{width:1600,height:900},recordVideo:{dir:work,size:{width:1600,height:900}}});
 const page=await context.newPage(),start=Date.now();const seconds=()=>Number(((Date.now()-start)/1000).toFixed(3));
 const titles=['SignalBrief: from announcement to a reviewed decision','Zapier RSS ingestion — historical published configuration','Slack review request — actual historical delivery','Slack approved report — actual historical delivery'];
 for(const title of titles){
  const old=report.chapters.find(x=>x.title===title),caption=title===titles[0]?'Real footage and outputs. The larger-packet trial failed; the successful retest used a 4,000-character source cap.':old.caption;
  const body=title===titles[0]
    ? '<div class="card"><h2>Detailed feature walkthrough</h2><p>Evidence collection → CrewAI researcher and verifier → AutoGen strategist, critic and editor → human decision → durable delivery record.</p><p>Fresh Notion tests, revision feedback and report history, approval, a labelled rejection replay, failed-source retry and cancellation, exports and mobile views.</p></div><div class="card"><b>What was actually recorded</b><p>Isolated local copy with real Groq inference. The initial trial failed; the bounded retest and its revision completed. Historical Linear and Slack evidence are labelled. No new Slack messages are sent.</p></div>'
    : `<div class="proof-crop ${title===titles[1]?'zapier':''}"><img src="/walkthrough-asset/${title===titles[1]?'zapier-rss-live.png':title===titles[2]?'slack-review.png':'slack-approved.png'}"></div>`;
  fs.writeFileSync(path.join(work,'proof.html'),`<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/static/walkthrough-only.css"></head><body><div class="tag">SIGNALBRIEF / WALKTHROUGH EVIDENCE</div><h1>${escape(title)}</h1><p class="muted">${escape(caption)}</p>${body}</body></html>`);
  const at=seconds();await page.goto(base+'/walkthrough-proof');await pause(5500);
  if(title!==titles[0])await page.locator('.proof-crop').evaluate(el=>el.classList.add('zoom'));
  await pause(7500);await page.screenshot({path:path.join(work,'zoom-'+titles.indexOf(title)+'.png')});
  const board=report.boards.find(x=>x.title===title);Object.assign(board,{start:at,end:seconds(),source:'evidence-zoom.webm'});old.caption=caption;
 }
 const video=page.video();await context.close();await video.saveAs(path.join(work,'evidence-zoom.webm'));await browser.close();
 fs.writeFileSync(path.join(work,'boards-report.json'),JSON.stringify(report,null,2));console.log('Original evidence captured with readable zooms.');
})().catch(e=>{console.error(e.message);process.exitCode=1;});
