<script lang="ts">
 import {onMount,onDestroy,tick} from 'svelte';
 import ConversationHistory from '$lib/ConversationHistory.svelte';
 import FilterControls from '$lib/FilterControls.svelte';
 import Answer from '$lib/Answer.svelte';
 import TurnEvidence from '$lib/TurnEvidence.svelte';
 import type {Conversation} from '$lib/conversations';
 import type {Trace,Generation} from '$lib/types';
 import type {ExactFilters} from '$lib/filters';
 import {answerPath,streamAnswer} from '$lib/answer-stream';
 let question='';let traces:Trace[]=[];let filters:ExactFilters={};let conversationId:string|null=null;
 let history:ConversationHistory;let busy=false;let navigationLoading=false;let generating=false;let ready=false;let error='';
 let providerMessage='Remote generation is not configured.';let mode='keyword';let operation=0;
 let controller:AbortController|null=null;let active:Trace|null=null;let historyOpen=false;let filtersOpen=false;
 let settings={keyword_candidates:20,vector_candidates:20,rrf_constant:60,evidence_limit:8,rerank_candidates:40};
 function select(conversation:Conversation|null){traces=conversation?.turns.map(turn => turn.trace)||[];filters=structuredClone(conversation?.current_filters||{});mode=conversation?.current_mode||mode;question='';error='';historyOpen=false;}
 function update(turn:Trace,generation:Generation){traces=traces.map(t => t.turn_id===turn.turn_id ? {...t,generation} : t);}
 async function persistFilters(){await tick();try{await history.persistFilters(filters);}catch(e){error=e instanceof Error?e.message:'Filters could not be saved.';}}
 async function persistMode(value:string){try{await history.persistMode(value);}catch(e){error=e instanceof Error?e.message:'Search mode could not be saved.';}}
 onMount(async()=>{ready=true;try{providerMessage=(await(await fetch('/api/provider')).json()).message;}catch{providerMessage='Provider status is unavailable. Retrieval remains available.';}});
 onDestroy(()=>controller?.abort());
 async function search(event:SubmitEvent){
  event.preventDefault();if(busy || navigationLoading)return;busy=true;error='';const current=++operation;const submitted=question;
  try{
   await history.flush();const id=await history.ensureConversation();
   const response=await fetch('/api/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:submitted,mode,settings,filters,generate_answer:false,conversation_id:id})});
   const result=await response.json();
   if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:Array.isArray(result.detail)?result.detail.map((item:{msg:string})=>item.msg).join(' '):'Search failed. Check the question and filters.');
   const turn:Trace=result;active=turn;traces=[...traces,turn];question='';
   await history.saved(turn);
   controller=new AbortController();generating=true;
   await streamAnswer(turn,generation=>{if(operation===current)update(turn,generation);},controller.signal);
   // The stream is authoritative for this in-flight response. Refresh navigation only;
   // production saves terminal output before sending done.
   if(operation===current)await history.saved(turn);
  }catch(e){if(operation===current){error=e instanceof Error?e.message:'Search failed. Try again.';if(generating&&active){const latest=traces.find(t=>t.turn_id===active?.turn_id);if(latest)update(latest,{...latest.generation,status:'failed',message:'The answer connection failed. Partial output is incomplete; retrieved evidence is preserved.',citations:[],assets:[]});}}}
  finally{if(operation===current){busy=false;generating=false;controller=null;active=null;}}
 }
 async function stopAnswer(){
  const turn=active;const abort=controller;if(!turn||!abort)return;
  const current=++operation;busy=false;generating=false;controller=null;active=null;
  const latest=traces.find(t=>t.turn_id===turn.turn_id)||turn;
  update(turn,{...latest.generation,status:'cancelled',message:'Answer stopped. Partial output is incomplete.',citations:[],assets:[]});abort.abort();
  const isCurrent=()=>operation===current&&conversationId===turn.conversation_id;
  try{const response=await fetch(answerPath(turn,'cancel'),{method:'POST',signal:AbortSignal.timeout(3000)});if(!response.ok)throw new Error();const generation=await response.json();if(isCurrent())update(turn,generation.status==='cancelled'?{...generation,message:'Answer stopped. Partial output is incomplete.'}:generation);}
  catch{if(isCurrent())error='Stop could not reach the service within three seconds. The stream connection was closed; partial output is incomplete.';}
 }
</script>
<svelte:head><title>Magic RAG — Card conversations</title><meta name="description" content="Discover Magic cards through grounded conversation."/></svelte:head>
<div class="app-shell">
 <aside class="history-panel" class:open={historyOpen} aria-label="Chat history">
  <div class="brand"><span aria-hidden="true">✦</span><strong>Magic RAG</strong><button class="mobile-close" aria-label="Close history" onclick={()=>historyOpen=false}>×</button></div>
  <ConversationHistory bind:this={history} bind:conversationId bind:loading={navigationLoading} {busy} {mode} onselect={select}/>
  <div class="local">● Local card workspace</div>
 </aside>
 <main>
  <header><button class="panel-toggle" aria-expanded={historyOpen} onclick={()=>{historyOpen=!historyOpen;filtersOpen=false;}}>Chats</button><span>Card conversations</span><button class="panel-toggle" aria-expanded={filtersOpen} onclick={()=>{filtersOpen=!filtersOpen;historyOpen=false;}}>Filters</button></header>
  <div class="transcript" aria-label="Conversation transcript" aria-live="polite">
   {#if !traces.length}<div class="welcome"><div class="symbol" aria-hidden="true">✦</div><p class="eyebrow">MAGIC: THE GATHERING</p><h1>What will you discover?</h1><p>Find a card. Explore an ability.<br/>Follow the evidence.</p></div>{/if}
   {#each traces as trace (trace.turn_id || trace.trace_id)}
    {@const prefix=`turn-${trace.turn_id || trace.trace_id}`}
    <section class="turn" aria-label={`Turn: ${trace.question}`}>
     <div class="question"><span class="speaker">YOU</span><p>{trace.question}</p></div>
     <div class="response"><span class="speaker">MAGIC RAG</span><Answer generation={trace.generation} {prefix}/><TurnEvidence {trace} {prefix}/></div>
    </section>
   {/each}
  </div>
  <div class="composer">
   {#if error}<p class="error" role="alert">{error}</p>{/if}
   <form onsubmit={search}>
    <label class="sr-only" for="question">Your question</label><textarea id="question" bind:value={question} disabled={navigationLoading || !ready} placeholder="Ask about a card or describe an ability…" required maxlength="10000" rows="2"></textarea>
    <div class="composer-foot"><div><label class="sr-only" for="mode">Search mode</label><select id="mode" bind:value={() => mode, value => {mode=value;void persistMode(value);}} disabled={busy || navigationLoading || !ready}><option value="keyword">Keyword · BM25</option><option value="vector">Vector · local embeddings</option><option value="hybrid">Hybrid · rank fusion</option><option value="hybrid_rerank">Hybrid + cross-encoder</option></select></div>{#if generating}<button type="button" class="stop" onclick={stopAnswer}>Stop answer ■</button>{:else}<button class="send" disabled={busy || navigationLoading || !ready || !question.trim()}>{busy?'Retrieving…':'Send'}</button>{/if}</div>
   </form>
   <p class="provider">{providerMessage}</p>
  </div>
 </main>
 <aside class="filters-panel" class:open={filtersOpen} aria-label="Filters">
  <div class="panel-heading"><h2>Filters</h2><button class="mobile-close" aria-label="Close filters" onclick={()=>filtersOpen=false}>×</button></div><p class="panel-intro">For your next message</p>
  <FilterControls bind:filters={() => filters, value => {filters=value;void persistFilters();}} disabled={busy || navigationLoading || !ready}/>
  <details class="settings"><summary>Retrieval settings</summary><div class="settings-grid">
   <label>Keyword candidates<input type="number" min="1" max="1000" required bind:value={settings.keyword_candidates}/></label><label>Vector candidates<input type="number" min="1" max="1000" required bind:value={settings.vector_candidates}/></label><label>Fusion constant<input type="number" min="0" max="10000" required bind:value={settings.rrf_constant}/></label><label>Evidence limit<input type="number" min="1" max="1000" required bind:value={settings.evidence_limit}/></label><label>Reranker shortlist<input type="number" min="1" max="1000" required bind:value={settings.rerank_candidates}/></label>
  </div></details>
 </aside>
</div>
<style>
 :global(*){box-sizing:border-box}:global(html){color-scheme:dark}:global(body){margin:0;background:#181c1a;color:#e3e9df;font:14px 'Segoe UI',sans-serif}:global(button),:global(textarea),:global(select),:global(input){font:inherit}:global(button){cursor:pointer}:global(button:disabled){opacity:.45;cursor:default}:global(:focus-visible){outline:2px solid #b4d49d;outline-offset:4px}:global(a){color:#b4d49d}.app-shell{display:grid;grid-template-columns:240px minmax(0,1fr) 290px;min-height:100dvh}.history-panel,.filters-panel{padding:24px 18px;min-width:0;background:#111613;position:sticky;top:0;height:100dvh;overflow-y:auto}.history-panel{display:flex;flex-direction:column;border-right:1px solid #2b352d}.brand{display:flex;gap:12px;align-items:center;margin:5px 10px 32px;font-size:15px;letter-spacing:.02em}.brand>span{font-size:25px;color:#b4d49d}.brand strong{font-weight:600}.local{margin-top:auto;padding:40px 10px 0;color:#8c9d8e;font-size:10px;letter-spacing:.03em}main{min-width:0;display:flex;flex-direction:column;min-height:100dvh}header{height:70px;display:flex;align-items:center;justify-content:center;gap:16px;border-bottom:1px solid #29322c;color:#a4b1a4;font-size:12px;letter-spacing:.04em}.panel-toggle,.mobile-close{display:none}.transcript{width:100%;max-width:850px;margin:0 auto;padding:24px 40px 40px;flex:1;min-width:0}.welcome{padding:15vh 0 10vh;text-align:center}.symbol{font-size:38px;color:#b4d49d}.eyebrow{font-size:9px!important;letter-spacing:.2em;margin-top:20px!important;color:#99ad94}h1{font:36px/1.2 Georgia,serif;letter-spacing:-.03em;margin:18px 0}.welcome p{font-size:14px;line-height:1.9;color:#9aa99b}.turn{padding:20px 0 32px;min-width:0}.question{background:#27312a;padding:16px 20px;border-radius:12px 12px 0 12px;margin:0 0 28px auto;max-width:90%;overflow-wrap:anywhere}.question p{margin:7px 0 0;white-space:pre-wrap;line-height:1.7}.speaker{font-size:9px;letter-spacing:.16em;color:#9db096}.response{min-width:0}.composer{position:sticky;bottom:0;width:100%;max-width:850px;margin:auto;padding:16px 32px 12px;background:#181c1a}.composer form{border:1px solid #465249;background:#222a24;border-radius:14px;padding:15px}.composer textarea{display:block;width:100%;resize:vertical;max-height:240px;min-height:55px;border:0;background:transparent;color:#e3e9df;line-height:1.7;padding:2px 3px}.composer textarea:focus{outline:none}.composer:focus-within form{border-color:#8ca67e}.composer-foot{display:flex;align-items:center;justify-content:space-between;gap:10px}.composer select{background:#222a24;color:#b3c0b2;border:0;padding:8px 0;font-size:11px;max-width:100%}.composer-foot>div{min-width:0}.send,.stop{border:0;border-radius:8px;padding:10px 16px;background:#b4d49d;color:#182319;font-weight:600;font-size:12px;white-space:nowrap}.stop{background:#d6bd91}.provider{font-size:10px;line-height:1.6;color:#99a698;text-align:center;margin:10px 4px 0}.error{font-size:12px;line-height:1.6;color:#f1bcb2}.filters-panel{border-left:1px solid #2b352d;padding:30px 15px}.panel-heading{display:flex;align-items:center;justify-content:space-between}.panel-heading h2{font:21px Georgia,serif;margin:0}.panel-intro{font-size:11px;color:#9aa99b;margin:10px 0 22px}.settings{margin:25px 0;color:#aab9a7;font-size:11px}summary{cursor:pointer}.settings-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:15px;margin-top:18px}.settings label{font-size:10px;line-height:1.5}.settings input{display:block;width:100%;margin-top:7px;padding:8px;border:1px solid #435247;border-radius:4px;background:#202721;color:#e3e9df}.sr-only{position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}@media(max-width:1180px){.app-shell{grid-template-columns:205px minmax(0,1fr) 260px}.transcript{padding:24px}.composer{padding:12px 20px}.history-panel{padding:24px 12px}}@media(max-width:950px){.app-shell{display:block}header{justify-content:space-between;padding:0 20px;height:60px}.panel-toggle,.mobile-close{display:block;background:transparent;border:1px solid #465249;border-radius:6px;color:#d7e3d1;padding:8px 11px;font-size:12px}.mobile-close{margin-left:auto;font-size:18px;padding:3px 10px}.history-panel,.filters-panel{display:none;position:fixed;top:60px;bottom:0;height:calc(100dvh - 60px);z-index:5;width:min(320px,90vw);box-shadow:0 12px 36px #0008}.history-panel.open{display:flex;left:0}.filters-panel.open{display:block;right:0}.welcome{padding:12vh 0 8vh}h1{font-size:31px}.transcript{padding:20px}.composer{padding:10px 14px}.question{max-width:95%}.brand{margin-bottom:25px}.settings-grid{gap:12px}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
</style>
