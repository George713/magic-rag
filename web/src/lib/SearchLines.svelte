<script lang="ts">
 import {describeFilters} from '$lib/filters';
 import {revealEvidence} from '$lib/evidence';
 import type {Trace} from '$lib/types';
 /** A turn's searches: live lines while it runs, then one collapsed "N searches" summary holding the retrieval details. */
 let {trace,prefix}:{trace:Trace;prefix:string}=$props();
 const cards=(count:number)=>`${count} ${count===1?'card':'cards'}`;
 const running=$derived(['searching','generating'].includes(trace.generation.status));
 const count=$derived(trace.searches.length);
</script>
{#snippet lines()}
 <ol class="searches" aria-label="Searches">
  {#each trace.searches as search}<li><span class="query">searching "{search.query}"</span> · <span class="count">{cards(search.selected_evidence.length)}</span></li>{/each}
 </ol>
{/snippet}
{#if running}
 {#if count}{@render lines()}{/if}
{:else if count}
 <details class="retrieval-details search-summary">
  <summary><span class="summary-count">{count} {count===1?'search':'searches'}</span> <span class="summary-hint">Retrieval details</span></summary>
  {@render lines()}
  <aside aria-label="Retrieval inspector">
   <dl><dt>Original question</dt><dd data-testid="original-question">{trace.question}</dd><dt>Active corpus</dt><dd>{trace.corpus?.id || 'No active corpus'}</dd><dt>Retrieval time</dt><dd>{trace.timings_ms.retrieval === undefined ? 'pending' : `${trace.timings_ms.retrieval.toFixed(2)} ms`}</dd></dl>
   {#each trace.searches as search,index}
    <section class="search" aria-label={`Search ${index+1}`}>
     <h4 class="search-title">Search {index+1} <span>{cards(search.selected_evidence.length)}</span></h4>
     <dl><dt>Actual search query</dt><dd data-testid="actual-query">{search.query}</dd><dt>Mode</dt><dd>{search.mode}</dd><dt>Search filters</dt><dd data-testid="trace-filters">{describeFilters(search.filters)}</dd></dl>
     {#each Object.entries(search.stages) as [stage,cards]}
      <h4>{stage === 'reranked' ? 'Reranked' : stage === 'fused' ? 'Fused' : stage === 'vector' ? 'Vector' : 'Keyword'} candidates <span>{cards.length}</span></h4>
      <p class="score-note">{stage === 'reranked' ? search.settings.reranker_metric : stage === 'fused' ? search.settings.fusion_metric : stage === 'vector' ? search.settings.vector_metric : 'BM25 · lower scores rank first'}</p>
      <ol>{#each cards as card}<li><div><a href={`#${prefix}-card-${card.card_id}`} onclick={revealEvidence}>{card.rank}. {card.name}</a>{#if card.fused_rank !== undefined}<p class="signals">Fused #{card.fused_rank} → #{card.rank} · {card.rank_change! > 0 ? `promoted ${card.rank_change}` : card.rank_change! < 0 ? `demoted ${-card.rank_change!}` : 'unchanged'}</p>{/if}{#if card.signals}<p class="signals">{#each Object.entries(card.signals) as [branch,signal]}<span>{branch} #{signal.rank} · {signal.score.toPrecision(4)}</span>{/each}</p>{/if}</div><code>{card.score.toPrecision(4)}</code></li>{/each}</ol>
     {/each}
     <dl><dt>Stage timings</dt><dd data-testid="search-timings">{#each Object.entries(search.timings_ms) as [stage,ms]}<div>{stage}: {ms.toFixed(2)} ms</div>{/each}</dd><dt>Effective settings</dt><dd><pre>{JSON.stringify(search.settings,null,2)}</pre></dd></dl>
     {#each Object.entries(search.models) as [name,model]}<dl><dt>{name} model</dt><dd><pre>{JSON.stringify(model,null,2)}</pre></dd></dl>{/each}
    </section>
   {/each}
   <dl><dt>Turn timings</dt><dd>{#each Object.entries(trace.timings_ms) as [stage,ms]}<div>{stage}: {ms.toFixed(2)} ms</div>{/each}</dd></dl>
   <details><summary>Complete trace</summary><pre>{JSON.stringify(trace,null,2)}</pre></details>
  </aside>
 </details>
{/if}
<style>
 .searches{list-style:none;margin:10px 0 0;padding:0;display:grid;gap:4px;font:12px/1.6 'Segoe UI',sans-serif;color:#9aa99b;min-width:0}.searches li{display:block;padding:0;border:0}.query{color:#c7d4c2;overflow-wrap:anywhere}.count{white-space:nowrap}
 .retrieval-details{margin-top:12px;border:1px solid #354038;border-radius:8px;padding:11px 16px;font-size:12px;color:#b6c3b5;min-width:0}summary{cursor:pointer;overflow-wrap:anywhere}.summary-count{color:#c7d4c2}.summary-hint{margin-left:10px;color:#9aa99b;font-size:11px}.search-summary[open] .searches{margin-bottom:6px}
 aside{padding-top:8px;min-width:0}dt{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#9aa99b;margin-top:18px}dd{margin:6px 0 0;line-height:1.7;overflow-wrap:anywhere}h4{margin:25px 0 0;font-size:13px;display:flex;justify-content:space-between;gap:10px}.score-note,.signals{font-size:10px;color:#9aa99b}.signals span{display:block}ol{list-style:none;padding:0}li{display:flex;justify-content:space-between;gap:15px;padding:12px 0;border-top:1px solid #344037;min-width:0}li>div{min-width:0;overflow-wrap:anywhere}a{color:#b4d49d;text-underline-offset:3px}code{font-size:10px}.search{margin-top:22px;padding-top:4px;border-top:1px solid #465249;min-width:0}.search-title{margin-top:14px;font:15px Georgia,serif;color:#e3e9df}.search-title span{font:11px 'Segoe UI',sans-serif;color:#9aa99b}pre{max-height:350px;overflow:auto;font-size:10px;white-space:pre-wrap;overflow-wrap:anywhere}
</style>
