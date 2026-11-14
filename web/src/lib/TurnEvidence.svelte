<script lang="ts">
 import type {Trace} from '$lib/types';
 import CardImages from '$lib/CardImages.svelte';
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
<style>
 .evidence{min-width:0;margin-top:18px;border:1px solid #354038;border-radius:8px;padding:13px 16px;font-size:12px;color:#b6c3b5}.evidence>summary span{margin-left:10px;color:#9aa99b;font-size:11px}article{padding:20px 0;border-bottom:1px solid #344037;scroll-margin-top:20px}.card-heading{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}.rank{font:10px Consolas,monospace;color:#9aa99b}h3{font:22px/1.3 Georgia,serif;margin:0;color:#e3e9df}.mana{margin-left:auto;font:12px Consolas,monospace}.properties,.card-source{font-size:11px;color:#9aa99b;line-height:1.7;overflow-wrap:anywhere}.card-text{white-space:pre-wrap;font:15px/1.8 Georgia,serif;overflow-wrap:anywhere}.empty{padding:20px 0;color:#9aa99b;font-size:13px;line-height:1.7}summary{cursor:pointer}
</style>
