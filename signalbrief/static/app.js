'use strict';
const publicView = document.body.dataset.mode === 'showcase';
const $ = (id) => document.getElementById(id);
let csrf = '', runs = [], competitors = [], selected = new URLSearchParams(location.search).get('run');
let currentRun = null, activeTab = 'brief', refreshTimer, eventId = crypto.randomUUID();
const labels = {queued:'Queued',running:'Researching',awaiting_approval:'Needs review',approved:'Approved',
  rejected:'Rejected',failed:'Failed',sent:'Accepted by Zapier',pending:'Delivery pending',blocked:'Configuration needed',
  cancelled:'Cancelled',sending:'Sending'};
const el = (tag, className, text) => { const n = document.createElement(tag); if(className)n.className=className;
  if(text !== undefined)n.textContent=text; return n; };
const badge = (status) => el('span', 'badge '+status, labels[status] || status);
const date = (seconds) => new Date(seconds * 1000).toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
const section = (parent,title) => parent.appendChild(el('div','section-heading',title));
const paragraph = (parent,text,className='') => parent.appendChild(el('p',className,text));
const list = (parent,items) => { const ul=el('ul'); items.forEach(s=>ul.append(el('li','',s)));parent.append(ul); };
const link = (url,text) => { const a=el('a','',text); const u=new URL(url,location.origin);
  if(u.protocol!=='https:' && u.origin!==location.origin)return el('span','',text);
  a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';return a; };

async function api(path, options={}) {
  if(publicView){
    if(options.method && options.method!=='GET')throw new Error('This published workspace is read-only.');
    path=path.replace('/api/runs','/api/showcase/runs').replace('/api/status','/api/showcase/status');
  }
  const headers={'Content-Type':'application/json',...options.headers};
  if(options.method && options.method!=='GET')headers['X-CSRF-Token']=csrf;
  const response=await fetch(path,{...options,headers,credentials:'same-origin'});
  const content=await response.json();
  if(!response.ok){
    if(response.status===401 && path!=='/api/login'){showLogin();}
    throw new Error(typeof content.detail==='string'?content.detail:'The request could not be completed.');
  }
  return content;
}
function toast(text){$('toast').textContent=text;$('toast').hidden=false;setTimeout(()=>$('toast').hidden=true,6000);}
function showLogin(){clearInterval(refreshTimer);$('workspace').hidden=true;$('login').hidden=false;}
async function startWorkspace(){
  $('login').hidden=true;$('workspace').hidden=false;
  if(publicView){
    for(const id of ['new-signal','nav-new','logout'])$(id).hidden=true;
    document.querySelector('header .muted').textContent='Read-only execution evidence from two approved live runs. Open Evidence, Agent record, or Activity & delivery to inspect the proof.';
    $('configuration').hidden=false;$('configuration').textContent='Published portfolio workspace. Research ran with real Groq, CrewAI and AutoGen; the recorded Slack deliveries happened before cloud deployment.';
  }
  competitors=publicView?[]:await api('/api/competitors');$('competitor').replaceChildren();
  competitors.forEach(c=>{const option=el('option','',c.name);option.value=c.name;$('competitor').append(option);});
  updateCompetitor();await refresh();clearInterval(refreshTimer);refreshTimer=setInterval(()=>refresh().catch(e=>toast(e.message)),5000);
}
function updateCompetitor(){const c=competitors.find(c=>c.name===$('competitor').value);if(!c)return;
  $('competitor-context').textContent=c.our_context;$('allowed-domains').textContent='Allowed sources: '+c.domains.join(', ');}
function openEvent(){ $('event-error').textContent='';$('event-dialog').showModal(); }

async function refresh(force=false){
  const [newRuns,status]=await Promise.all([api('/api/runs'),api('/api/status')]);runs=newRuns;
  $('worker-state').textContent=status.worker_online?'Worker online':'Worker offline';
  const missing=[];if(!status.model_configured)missing.push('Configure a model API key in .env.');
  if(!status.zapier_configured)missing.push('Configure ZAPIER_HOOK_URL for real delivery.');
  if(!status.worker_online)missing.push('Start the worker to process new signals.');
  if(!publicView){$('configuration').hidden=!missing.length;$('configuration').textContent=missing.join(' ');}
  $('count-all').textContent=runs.length;
  $('count-review').textContent=runs.filter(r=>r.status==='awaiting_approval').length;
  $('count-approved').textContent=runs.filter(r=>r.status==='approved').length;
  $('count-processing').textContent=runs.filter(r=>['queued','running'].includes(r.status)).length;
  if(publicView && !selected && runs.length)selected=runs[0].id;
  renderRuns();
  if(selected){const next=await api('/api/runs/'+selected);
    const changed=!currentRun||next.updated_at!==currentRun.updated_at||next.status!==currentRun.status||
      JSON.stringify(next.deliveries)!==JSON.stringify(currentRun.deliveries);
    // Don't destroy a human's in-progress review feedback while polling delivery changes.
    if(force||changed && !($('review-feedback')?.value && document.activeElement===$('review-feedback'))){
      currentRun=next;renderDetail();}
  }
}
function renderRuns(){const parent=$('run-list');parent.replaceChildren();const filter=$('filter').value;
  const filtered=runs.filter(r=>filter==='all'||r.status===filter);
  if(!filtered.length){const empty=el('div','empty');empty.append(el('h3','','No signals yet'),el('p','','Capture an announcement or connect your RSS Zap.'));parent.append(empty);return;}
  for(const run of filtered){const b=el('button','run-card'+(selected===run.id?' selected':''));
    const row=el('div','row');row.append(el('span','company-label',run.event.competitor),badge(run.status));
    b.append(row,el('h3','',run.event.title));const lower=el('div','row');lower.append(el('span','time',date(run.created_at)),el('span','time','v'+run.version+' ↗'));b.append(lower);
    b.onclick=async()=>{selected=run.id;currentRun=null;activeTab='brief';history.replaceState(null,'','?run='+selected);await refresh(true);};parent.append(b);
  }
}
function renderDetail(){const r=currentRun,parent=$('detail');parent.replaceChildren();if(!r)return;
  const head=el('div','detail-header');const row=el('div','row');row.append(el('span','company-label',r.event.competitor+' / SIGNAL BRIEF'),badge(r.status));
  head.append(row,el('h2','',r.research?.headline||r.event.title));const meta=el('div','detail-meta');
  meta.append(el('span','','Captured '+date(r.created_at)),el('span','','Version '+r.version),el('span','',(r.sources?.length||0)+' sources'));
  if(r.report)meta.append(link((publicView?'/api/showcase/runs/':'/api/runs/')+r.id+'/report.md','↓ Export brief'));
  head.append(meta);parent.append(head);
  const tabs=el('div','tabs');for(const [id,title] of [['brief','Strategy brief'],['evidence','Evidence'],['agents','Agent record'],['activity','Activity & delivery']]){
    const b=el('button','tab'+(activeTab===id?' active':''),title);b.onclick=()=>{activeTab=id;renderDetail();};tabs.append(b);}
  parent.append(tabs);const body=el('div','detail-body');parent.append(body);
  if(activeTab==='brief')renderBrief(body,r);
  if(activeTab==='evidence')renderEvidence(body,r);
  if(activeTab==='agents')renderAgents(body,r);
  if(activeTab==='activity')renderActivity(body,r);
  if(r.status==='awaiting_approval'&&activeTab==='brief')renderReview(parent,r);
  if(r.status==='failed'){const bar=el('div','review-bar');const button=el('button','secondary','Retry failed run');
    button.onclick=()=>perform(button,async()=>{await api('/api/runs/'+r.id+'/retry',{method:'POST'});await refresh(true);});bar.append(button);parent.append(bar);}
  if(['queued','failed'].includes(r.status)){const bar=el('div','review-bar');const button=el('button','secondary danger','Cancel run');
    button.onclick=()=>perform(button,async()=>{await api('/api/runs/'+r.id+'/cancel',{method:'POST'});toast('Run cancelled. Its evidence and history are retained.');await refresh(true);});bar.append(button);parent.append(bar);}
}
function renderBrief(body,r){
  if(r.error)paragraph(body,r.error,'error');
  if(!r.research){paragraph(body,r.status==='failed'?'This run failed before producing a verified dossier.':'Evidence collection and research will appear here as the worker progresses.','muted');
    paragraph(body,'Current stage: '+r.stage,'callout');return;}
  section(body,'Research summary');paragraph(body,r.research.summary);
  section(body,'Evidence-backed findings');const sources=Object.fromEntries((r.sources||[]).map(s=>[s.source_id,s]));
  for(const finding of r.research.findings){const card=el('div','finding');paragraph(card,finding.claim);
    for(const citation of finding.citations){const q=el('blockquote','quote',citation.excerpt);const source=sources[citation.source_id];
      if(source)q.append(link(source.url,source.title+' ↗'));card.append(q);}body.append(card);}
  if(!r.report){paragraph(body,r.status==='cancelled'?'This run was cancelled.':r.status==='failed'?'Analysis failed; retry or cancel this run.':'The analysis council is still working.','callout');return;}
  section(body,'Strategic interpretation · hypotheses');paragraph(body,r.report.strategic_summary);list(body,r.report.implications);
  section(body,'Proposed actions');for(const action of r.report.actions){const card=el('div','action-card');
    card.append(el('div','action-meta',action.priority+' priority / '+action.owner),el('h3','',action.action));paragraph(card,action.rationale);
    paragraph(card,'Validate: '+action.validation_step,'validation');for(const id of action.evidence_ids){if(sources[id])card.append(link(sources[id].url,'Source ↗ '));}body.append(card);}
  section(body,'What the critic challenged');list(body,r.report.challenged_assumptions);
  section(body,'Unknowns & limitations');list(body,[...r.research.unknowns,...r.report.limitations,...(r.metrics?.source_warnings||[])]);
  paragraph(body,'Quotes are checked against fetched text. Strategic implications remain hypotheses; citations do not prove market impact.','callout');
  if(r.history.length>1){section(body,'Report history');for(const version of r.history){const d=el('details');d.append(el('summary','','Version '+version.version+' · '+date(version.created_at)));
    paragraph(d,version.report.strategic_summary);list(d,version.report.actions.map(a=>a.action));body.append(d);}}
}
function renderEvidence(body,r){section(body,'Frozen source evidence');paragraph(body,'These are the actual public-page texts used for this run. Fetch times and text hashes preserve the research record.','muted');
  if(!r.sources?.length){paragraph(body,'Evidence has not been collected yet.','muted');return;}
  for(const source of r.sources){const d=el('details');d.append(el('summary','',source.title));d.append(link(source.url,source.url));
    paragraph(d,'Fetched '+new Date(source.fetched_at).toLocaleString(),'muted small');paragraph(d,'ID '+source.source_id+' · SHA-256 '+source.sha256,'muted small');
    d.append(el('div','evidence-text',source.text));body.append(d);}
}
function renderAgents(body,r){section(body,'Actual framework execution');paragraph(body,'Stored task outputs and council messages. This record contains source-backed outputs, not private model reasoning.','muted');
  if(!r.messages?.length)paragraph(body,'Agent outputs have not been saved yet.','muted');
  for(const message of r.messages||[]){const d=el('details');d.append(el('summary','',message.framework+' / '+message.agent));
    if(message.prompt_tokens!==undefined)paragraph(d,`${message.prompt_tokens} input tokens · ${message.completion_tokens} output tokens`,'muted small');
    d.append(el('pre','transcript',message.content));body.append(d);}
  section(body,'Research-only baseline');if(r.research)list(body,r.research.baseline_actions.map(a=>a.action+' — '+a.validation_step));
  section(body,'Measured execution');const pre=el('pre','transcript',JSON.stringify(r.metrics||{},null,2));body.append(pre);
}
function renderActivity(body,r){section(body,'Delivery record');paragraph(body,'A successful receipt means Zapier accepted the webhook. Check Zap History to confirm the final Slack action.','muted');
  if(!r.deliveries.length)paragraph(body,'No deliveries have been scheduled.','muted');
  for(const delivery of r.deliveries){const card=el('div','finding');card.append(el('h3','',delivery.kind.replaceAll('_',' ')),badge(delivery.status));
    paragraph(card,'Attempt '+delivery.attempts+' · Delivery ID '+delivery.id,'muted small');if(delivery.error)paragraph(card,delivery.error,'error');
    if(['failed','blocked'].includes(delivery.status)){const b=el('button','secondary','Retry delivery');b.onclick=()=>perform(b,async()=>{await api('/api/deliveries/'+delivery.id+'/retry',{method:'POST'});await refresh(true);});card.append(b);}body.append(card);}
  section(body,'Workflow history');for(const entry of r.audit){const row=el('div','audit-row');row.append(el('div','',entry.event.replaceAll('_',' ')),el('small','',date(entry.created_at)));
    if(Object.keys(entry.details).length)row.append(el('pre','transcript',JSON.stringify(entry.details,null,2)));body.append(row);}
}
function renderReview(parent,r){const bar=el('div','review-bar');bar.append(el('h3','','Your decision closes the loop'));
  paragraph(bar,'Approve this version for delivery, reject it, or request one revision.','muted small');
  const feedback=el('textarea');feedback.id='review-feedback';feedback.placeholder='Feedback or reason for your decision…';feedback.maxLength=2000;feedback.setAttribute('aria-label','Review feedback');bar.append(feedback);
  const buttons=el('div','review-buttons');for(const [decision,title,cls] of [['approve','Approve & deliver','primary'],['revise','Request revision','secondary'],['reject','Reject brief','secondary danger']]){
    if(decision==='revise'&&r.version>=2)continue;const b=el('button',cls,title);
    b.onclick=()=>perform(b,async()=>{if(decision==='revise'&&!feedback.value.trim())throw new Error('Add feedback before requesting a revision.');
      await api('/api/runs/'+r.id+'/review',{method:'POST',body:JSON.stringify({decision,version:r.version,feedback:feedback.value})});
      toast(decision==='approve'?'Approved. Delivery is queued.':decision==='revise'?'Revision queued with your feedback.':'Brief rejected.');await refresh(true);});buttons.append(b);}
  bar.append(buttons);parent.append(bar);
}
async function perform(button,action){button.disabled=true;try{await action();}catch(e){toast(e.message);}finally{button.disabled=false;}}
$('login-form').onsubmit=async(e)=>{e.preventDefault();const b=e.submitter;b.disabled=true;$('login-error').textContent='';
  try{const result=await api('/api/login',{method:'POST',body:JSON.stringify({password:$('password').value})});csrf=result.csrf;$('password').value='';await startWorkspace();}
  catch(error){$('login-error').textContent=error.message;}finally{b.disabled=false;}};
$('logout').onclick=()=>perform($('logout'),async()=>{await api('/api/logout',{method:'POST'});showLogin();const s=await api('/api/session');csrf=s.csrf;});
$('new-signal').onclick=openEvent;$('nav-new').onclick=openEvent;$('close-dialog').onclick=()=>$('event-dialog').close();
$('nav-signals').onclick=()=>window.scrollTo({top:0,behavior:'smooth'});$('competitor').onchange=updateCompetitor;$('filter').onchange=renderRuns;
$('event-form').onsubmit=async(e)=>{e.preventDefault();const b=e.submitter;b.disabled=true;$('event-error').textContent='';
  try{const published=$('published-at').value;const result=await api('/api/events',{method:'POST',body:JSON.stringify({event_id:eventId,
    competitor:$('competitor').value,title:$('event-title').value,source_url:$('source-url').value,published_at:published?new Date(published).toISOString():null})});
    selected=result.run_id;currentRun=null;activeTab='brief';eventId=crypto.randomUUID();$('event-dialog').close();$('event-title').value='';$('source-url').value='';
    history.replaceState(null,'','?run='+selected);await refresh(true);toast('Signal captured. Research is queued.');
  }catch(error){$('event-error').textContent=error.message;}finally{b.disabled=false;}};
(async()=>{try{if(publicView){await startWorkspace();return;}const session=await api('/api/session');csrf=session.csrf;if(session.authenticated)await startWorkspace();else showLogin();}catch(error){$('login-error').textContent=error.message;}})();
