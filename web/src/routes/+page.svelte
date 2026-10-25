<script lang="ts">
 import { onMount } from 'svelte';
 import Answer from '$lib/Answer.svelte';
 import ConversationHistory from '$lib/ConversationHistory.svelte';
 import FilterControls from '$lib/FilterControls.svelte';
 import { describeFilters, type ExactFilters } from '$lib/filters';
 import type { Trace } from '$lib/types';
 let question = '';
 let trace: Trace | null = null;
 let busy = false;
 let error = '';
 let conversationId: string | null = null;
 let history: ConversationHistory;
 let filters: ExactFilters = {};
 function showSaved(saved: Trace | null) {
  trace=saved; question=saved?.question || ''; error='';
  answerRequested=!!saved && !['unconfigured','ready'].includes(saved.generation.status);
  if (saved) filters = {...saved.filters};
 }
 let includeExplanation = false;
 let answerRequested = false;
 let providerMessage = 'Remote generation is not configured.';
 onMount(async () => {
  try { providerMessage = (await (await fetch('/api/provider')).json()).message; }
  catch { providerMessage = 'Provider status is unavailable. Retrieval remains available.'; }
 });
 let mode = 'keyword';
 let ready = false;
 onMount(() => { ready = true; });
 let settings = {keyword_candidates:20, vector_candidates:20, rrf_constant:60, evidence_limit:8, rerank_candidates:40};
 async function search(event: SubmitEvent) {
  event.preventDefault(); busy = true; error = '';
  const submittedQuestion = question;
  try {
   const id = await history.ensureConversation();
   const response = await fetch('/api/search', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({question:submittedQuestion, mode, settings, filters, generate_answer:includeExplanation, conversation_id:id})});
   const result = await response.json();
   if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : Array.isArray(result.detail) ? result.detail.map((item: {msg:string}) => item.msg).join(' ') : 'Search failed. Check the question and filters.');
   trace = result;
   answerRequested = includeExplanation;
   await history.saved(trace!);
  } catch (e) { error = e instanceof Error ? e.message : 'Search failed. Try again.'; }
  finally { busy = false; }
 }
</script>

<svelte:head><title>Magic RAG — Card research desk</title><meta name="description" content="Discover Magic cards and inspect your retrieval evidence."/></svelte:head>

<header><a class="brand" href="/">M<span>✦</span>R</a><div><strong>Magic RAG</strong><span class="subtitle">THE CARD RESEARCH DESK</span></div><span class="local"><i></i> Local workspace</span></header>
<main>
 <section class="workspace">
  <div class="eyebrow">01 / DISCOVER</div>
  <h1>A question.<br/>A trail of evidence.</h1>
  <p class="intro">Find cards by name or describe an ability. Follow the source text, one result at a time.</p>
  <ConversationHistory bind:this={history} bind:conversationId {busy} onselect={showSaved}/>
  <form onsubmit={search}>
   <label for="question">Your question</label>
   <textarea id="question" bind:value={question} placeholder="Try Lightning Bolt or Delver…" required maxlength="10000" rows="4"></textarea>
   <FilterControls bind:filters disabled={busy || !ready}/>
   <label class="answer-toggle"><input type="checkbox" bind:checked={includeExplanation} /> Include a cited explanation</label>
   <div class="form-foot"><div><label for="mode">Search mode</label><select id="mode" bind:value={mode} disabled={busy || !ready}><option value="keyword">Keyword · BM25</option><option value="vector">Vector · local embeddings</option><option value="hybrid">Hybrid · rank fusion</option><option value="hybrid_rerank">Hybrid + cross-encoder</option></select></div><button disabled={busy || !ready || !question.trim()}>{busy ? 'Searching…' : 'Search cards'} <span aria-hidden="true">↗</span></button></div>
   <details class="settings"><summary>Retrieval settings</summary><div class="settings-grid">
    <label>Keyword candidates<input type="number" min="1" max="1000" required bind:value={settings.keyword_candidates}/></label>
    <label>Vector candidates<input type="number" min="1" max="1000" required bind:value={settings.vector_candidates}/></label>
    <label>Fusion constant<input type="number" min="0" max="10000" required bind:value={settings.rrf_constant}/></label>
    <label>Evidence limit<input type="number" min="1" max="1000" required bind:value={settings.evidence_limit}/></label>
    <label>Reranker shortlist<input type="number" min="1" max="1000" required bind:value={settings.rerank_candidates}/></label>
   </div></details>
  </form>
  {#if error}<p class="error" role="alert">{error}</p>{/if}
  <div class="notice"><span>○</span><p>{providerMessage} Conversational rewriting is unavailable; your text is searched as-is.</p></div>
  {#if trace && answerRequested}<Answer generation={trace.generation} />{/if}
  <section class="evidence" aria-live="polite" aria-busy={busy}>
   <div class="section-title"><h2>Retrieved evidence</h2><span>{trace ? `${trace.selected_evidence.length} cards` : 'Awaiting a question'}</span></div>
   {#if trace}
    {#each trace.selected_evidence as card}
     <article id={`card-${card.card_id}`}><div class="card-heading"><span class="rank">{String(card.rank).padStart(2,'0')}</span><h3>{card.name}</h3><span class="mana">{card.mana_cost}</span></div><p class="properties">{card.type_line} · Mana value {card.mana_value} · {card.colors.join(', ') || 'Colorless'}</p><p class="card-text">{card.text}</p><div class="card-source">{card.card_id}</div></article>
    {:else}<div class="empty"><h3>No matching cards</h3><p>{trace.corpus ? 'Try a card name or different words from an ability.' : 'The corpus is empty. Run the sample ingestion command first.'}</p></div>{/each}
   {:else}<div class="empty"><span aria-hidden="true">✦</span><p>Your sources will appear here.</p></div>{/if}
  </section>
 </section>
 <aside aria-label="Retrieval inspector"><div class="eyebrow">02 / INSPECT</div><h2>The retrieval trail</h2><p class="aside-intro">The query, candidates, and evidence behind this search.</p>
  {#if trace}
   <dl><dt>Actual search query</dt><dd data-testid="actual-query">{trace.query}</dd><dt>Mode</dt><dd>{trace.mode}</dd><dt>Active corpus</dt><dd>{trace.corpus?.id || 'No active corpus'}</dd><dt>Search filters</dt><dd data-testid="trace-filters">{describeFilters(trace.filters)}</dd><dt>Retrieval time</dt><dd>{trace.timings_ms.retrieval.toFixed(2)} ms</dd></dl>
   {#each Object.entries(trace.stages) as [stage, cards]}
    <h3 class="stage-title">{stage === 'reranked' ? 'Reranked' : stage === 'fused' ? 'Fused' : stage === 'vector' ? 'Vector' : 'Keyword'} candidates <span>{cards.length}</span></h3><p class="score-note">{stage === 'reranked' ? trace.settings.reranker_metric : stage === 'fused' ? trace.settings.fusion_metric : stage === 'vector' ? trace.settings.vector_metric : 'BM25 · lower scores rank first'}</p>
    <ol>{#each cards as card}<li><div><a href={`#card-${card.card_id}`}>{card.rank}. {card.name}</a>{#if card.fused_rank !== undefined}<p class="signals">Fused #{card.fused_rank} → #{card.rank} · {card.rank_change! > 0 ? `promoted ${card.rank_change}` : card.rank_change! < 0 ? `demoted ${-card.rank_change!}` : 'unchanged'}</p>{/if}{#if card.signals}<p class="signals">{#each Object.entries(card.signals) as [branch,signal]}<span>{branch} #{signal.rank} · {signal.score.toPrecision(4)}</span>{/each}</p>{/if}</div><code>{card.score.toPrecision(4)}</code></li>{/each}</ol>
   {/each}
   <dl><dt>Stage timings</dt><dd>{#each Object.entries(trace.timings_ms) as [stage,ms]}<div>{stage}: {ms.toFixed(2)} ms</div>{/each}</dd><dt>Effective settings</dt><dd><pre>{JSON.stringify(trace.settings,null,2)}</pre></dd></dl>
   {#if trace.models.embedding}<dl><dt>Embedding model</dt><dd>{(trace.models.embedding as {model:string}).model}</dd><dt>Encoding configuration</dt><dd><pre>{JSON.stringify(trace.models.embedding,null,2)}</pre></dd></dl>{/if}
   {#if trace.models.reranker}<dl><dt>Reranker model</dt><dd>{(trace.models.reranker as {model:string}).model}</dd><dt>Reranker configuration</dt><dd><pre>{JSON.stringify(trace.models.reranker,null,2)}</pre></dd></dl>{/if}
   <details><summary>Complete trace</summary><pre>{JSON.stringify(trace,null,2)}</pre></details>
  {:else}<div class="inspector-empty">Submit a question to inspect its retrieval trail.</div>{/if}
 </aside>
</main>

<style>
 .settings{margin-top:20px}.settings-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:15px;margin-top:18px}.settings-grid label{font-size:11px}.settings-grid input{display:block;width:100%;margin-top:7px;padding:8px;border:1px solid #aab5a5;background:#fffefa;color:#243e30;font:inherit}.signals{font:9px/1.7 Consolas,monospace;color:#67735e;margin:6px 0 0}.signals span{display:block}
 .answer-toggle{display:flex;align-items:center;gap:8px;font-size:12px;font-weight:400;margin:13px 0}.answer-toggle input{accent-color:#294b38;width:16px;height:16px}
 :global(*){box-sizing:border-box} :global(body){margin:0;background:#f7f5ef;color:#242f29;font-family:'Segoe UI',sans-serif;font-size:15px} :global(button),:global(textarea){font:inherit} :global(a){color:inherit} :global(:focus-visible){outline:3px solid #ae6b34;outline-offset:4px} header{height:94px;display:flex;align-items:center;gap:15px;border-bottom:1px solid #d9ddd2;padding:0 5vw}.brand{font-family:Georgia,serif;font-size:23px;text-decoration:none;border:1px solid #243e30;padding:9px 10px}.brand span{font-size:14px;margin:0 3px}header strong{font-weight:600;letter-spacing:.02em}.subtitle{display:block;font-size:9px;letter-spacing:.18em;margin-top:5px}.local{margin-left:auto;font-size:12px;color:#536157}.local i{display:inline-block;width:6px;height:6px;border-radius:50%;background:#5f7b55;margin-right:7px}main{max-width:1440px;margin:auto;display:grid;grid-template-columns:minmax(0,1fr) 355px}.workspace{padding:48px 6vw 80px 5vw}.eyebrow{font-size:10px;letter-spacing:.2em;font-weight:600;color:#677366}h1{font:48px/1.12 Georgia,serif;letter-spacing:-.035em;margin:24px 0 18px}.intro{max-width:480px;line-height:1.7;color:#607065;margin-bottom:30px}label{display:block;font-weight:600;font-size:12px;margin-bottom:9px}textarea{width:100%;resize:vertical;border:1px solid #aab5a5;border-radius:2px;background:#fffefa;padding:16px;color:#242f29;min-height:115px;line-height:1.6}.form-foot{display:flex;justify-content:space-between;align-items:center;margin-top:10px;gap:15px}select{font:12px Segoe UI,sans-serif;padding:8px;background:#fffefa;border:1px solid #aab5a5;max-width:100%}button{border:0;border-radius:2px;background:#294b38;color:#fff;padding:13px 19px;cursor:pointer}button span{margin-left:18px}button:hover{background:#1e392a}button:disabled{opacity:.5;cursor:default}.notice{display:flex;gap:10px;color:#697063;margin:19px 0 38px;max-width:540px;font-size:11px;line-height:1.6}.notice p{margin:0}.notice>span{font-size:17px;line-height:1}h2{font:23px Georgia,serif;margin:0}.section-title{display:flex;align-items:baseline;justify-content:space-between;border-bottom:1px solid #cbd1c3;padding-bottom:16px;gap:15px}.section-title>span{font-size:10px;color:#68705f}.empty{padding:38px 0;color:#68705f}.empty>span{font-size:25px;color:#9ea68e}.empty h3{font:20px Georgia,serif;color:#344a39}.empty p{font-size:13px;line-height:1.6}article{padding:25px 0;border-bottom:1px solid #d9ddd2;scroll-margin-top:20px}.card-heading{display:flex;align-items:baseline;gap:12px}.rank{font:11px Consolas,monospace;color:#7b856f}h3{font:23px/1.3 Georgia,serif;margin:0}.mana{margin-left:auto;white-space:nowrap;font:12px Consolas,monospace}.properties{font-size:11px;color:#6b755f;margin:11px 0 20px}.card-text{white-space:pre-wrap;font:16px/1.7 Georgia,serif}.card-source{font:10px Consolas,monospace;color:#7b856f;margin-top:20px;overflow-wrap:anywhere}aside{padding:48px 30px;background:#edf0e6;border-left:1px solid #d8dece;min-width:0}aside h2{margin-top:24px}.aside-intro{font-size:12px;line-height:1.7;color:#68725f;margin:14px 0 30px}dt{font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:#69725f;margin-top:23px}dd{margin:7px 0 0;font-size:13px;line-height:1.6;overflow-wrap:anywhere}.stage-title{font:14px 'Segoe UI',sans-serif;margin-top:35px;display:flex;justify-content:space-between}.stage-title span{color:#69725f}.score-note{font-size:10px;color:#69725f}ol{list-style:none;padding:0}li{display:flex;justify-content:space-between;gap:15px;font-size:11px;padding:13px 0;border-top:1px solid #d2d9c9}li a{text-decoration:none;line-height:1.5}code{font-size:10px;color:#67735e}details{margin-top:30px}summary{font-size:11px;cursor:pointer}pre{font-size:10px;overflow:auto;max-height:450px}.inspector-empty{border-top:1px solid #cbd2c1;padding-top:25px;font-size:12px;line-height:1.7;color:#6f7866}.error{color:#9a392c;font-size:13px;line-height:1.5}@media(max-width:800px){main{grid-template-columns:1fr}.workspace{padding:30px 6vw}aside{border-left:0;border-top:1px solid #d8dece;padding:30px 6vw}h1{font-size:39px}header{height:78px;padding:0 6vw}.subtitle{font-size:8px}.local{font-size:10px}h3{font-size:20px}.card-heading{flex-wrap:wrap}.mana{margin-left:0}.section-title{align-items:center}.section-title>span{max-width:110px;text-align:right}}
</style>

