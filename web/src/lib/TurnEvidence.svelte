<script lang="ts">
 import {describeFilters} from '$lib/filters';
 import type {Trace} from '$lib/types';
 import CardImages from '$lib/CardImages.svelte';
 import {revealEvidence} from '$lib/evidence';
 export let trace:Trace;
 export let prefix:string;
</script>
<details class="evidence" aria-label="Retrieved evidence">
 <summary>Retrieved evidence <span>{trace.selected_evidence.length} cards</span></summary>
 {#each trace.selected_evidence as card}
  <article id={`${prefix}-card-${card.card_id}`}>
   <div class="card-heading"><span class="rank">{card.rank}</span><h3>{card.name}</h3><span class="mana">{card.mana_cost}</span></div>
   <p class="properties">{card.type_line} · Mana value {card.mana_value} · {card.colors.join(', ') || 'Colorless'}</p>
   <CardImages {card}/>
   <p class="card-text">{card.text}</p>
   <div class="card-source">{card.card_id}</div>
  </article>
 {/each}
</details>
{#if !trace.selected_evidence.length}<div class="empty"><h3>No matching cards</h3><p>Try changing your query or adjusting the filters. Your selected filters have been kept.</p></div>{/if}
<details class="retrieval-details">
 <summary>Retrieval details</summary>
 <aside aria-label="Retrieval inspector">
  <dl><dt>Original question</dt><dd data-testid="original-question">{trace.question}</dd><dt>Actual search query</dt><dd data-testid="actual-query">{trace.query}</dd><dt>Query rewriting</dt><dd data-testid="rewrite-status">{trace.rewrite.status}</dd><dt>Rewrite information</dt><dd data-testid="rewrite-message">{trace.rewrite.message}</dd><dt>Mode</dt><dd>{trace.mode}</dd><dt>Active corpus</dt><dd>{trace.corpus?.id || 'No active corpus'}</dd><dt>Search filters</dt><dd data-testid="trace-filters">{describeFilters(trace.filters)}</dd><dt>Retrieval time</dt><dd>{trace.timings_ms.retrieval.toFixed(2)} ms</dd></dl>
  {#each Object.entries(trace.stages) as [stage,cards]}
   <h4>{stage === 'reranked' ? 'Reranked' : stage === 'fused' ? 'Fused' : stage === 'vector' ? 'Vector' : 'Keyword'} candidates <span>{cards.length}</span></h4>
   <p class="score-note">{stage === 'reranked' ? trace.settings.reranker_metric : stage === 'fused' ? trace.settings.fusion_metric : stage === 'vector' ? trace.settings.vector_metric : 'BM25 · lower scores rank first'}</p>
   <ol>{#each cards as card}<li><div><a href={`#${prefix}-card-${card.card_id}`} onclick={revealEvidence}>{card.rank}. {card.name}</a>{#if card.fused_rank !== undefined}<p class="signals">Fused #{card.fused_rank} → #{card.rank} · {card.rank_change! > 0 ? `promoted ${card.rank_change}` : card.rank_change! < 0 ? `demoted ${-card.rank_change!}` : 'unchanged'}</p>{/if}{#if card.signals}<p class="signals">{#each Object.entries(card.signals) as [branch,signal]}<span>{branch} #{signal.rank} · {signal.score.toPrecision(4)}</span>{/each}</p>{/if}</div><code>{card.score.toPrecision(4)}</code></li>{/each}</ol>
  {/each}
  <dl><dt>Stage timings</dt><dd>{#each Object.entries(trace.timings_ms) as [stage,ms]}<div>{stage}: {ms.toFixed(2)} ms</div>{/each}</dd><dt>Effective settings</dt><dd><pre>{JSON.stringify(trace.settings,null,2)}</pre></dd></dl>
  {#each Object.entries(trace.models) as [name,model]}<dl><dt>{name} model</dt><dd><pre>{JSON.stringify(model,null,2)}</pre></dd></dl>{/each}
  <details><summary>Complete trace</summary><pre>{JSON.stringify(trace,null,2)}</pre></details>
 </aside>
</details>
<style>
 .evidence{min-width:0;margin-top:18px;border:1px solid #354038;border-radius:8px;padding:13px 16px;font-size:12px;color:#b6c3b5}.evidence>summary span{margin-left:10px;color:#9aa99b;font-size:11px}article{padding:20px 0;border-bottom:1px solid #344037;scroll-margin-top:20px}.card-heading{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}.rank{font:10px Consolas,monospace;color:#9aa99b}h3{font:22px/1.3 Georgia,serif;margin:0;color:#e3e9df}.mana{margin-left:auto;font:12px Consolas,monospace}.properties,.card-source{font-size:11px;color:#9aa99b;line-height:1.7;overflow-wrap:anywhere}.card-text{white-space:pre-wrap;font:15px/1.8 Georgia,serif;overflow-wrap:anywhere}.empty{padding:20px 0;color:#9aa99b;font-size:13px;line-height:1.7}.retrieval-details{margin-top:18px;border:1px solid #354038;border-radius:8px;padding:13px 16px;font-size:12px;color:#b6c3b5}summary{cursor:pointer}aside{padding-top:8px;min-width:0}dt{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#9aa99b;margin-top:18px}dd{margin:6px 0 0;line-height:1.7;overflow-wrap:anywhere}h4{margin:25px 0 0;font-size:13px;display:flex;justify-content:space-between}.score-note,.signals{font-size:10px;color:#9aa99b}.signals span{display:block}ol{list-style:none;padding:0}li{display:flex;justify-content:space-between;gap:15px;padding:12px 0;border-top:1px solid #344037}a{color:#b4d49d;text-underline-offset:3px}code{font-size:10px}pre{max-height:350px;overflow:auto;font-size:10px;white-space:pre-wrap;overflow-wrap:anywhere}
</style>
