<script lang="ts">
 import type { Generation } from '$lib/types';
 let { generation }: {generation: Generation} = $props();
</script>

<section class="answer" aria-label="Card explanation" aria-live="polite">
 <div class="heading"><h2>Card explanation</h2><span>{generation.status === 'completed' ? 'Evidence grounded' : generation.status.replaceAll('_', ' ')}</span></div>
 {#if generation.text}
  {#if generation.insufficient_evidence}<p class="insufficient">The selected evidence is insufficient to establish an answer.</p>{/if}
  <p class="text" data-testid="answer-text">{generation.text}</p>
  {#if generation.status === 'completed' && generation.citations?.length}
   <nav aria-label="Answer citations" data-testid="answer-citations"><span>Sources</span>{#each generation.citations as citation}<a href={`#card-${citation.card_id}`}>{citation.name} ↗</a>{/each}</nav>
  {/if}
  <p class="note">Check the card text below. This explanation is not an authoritative rules ruling.</p>
 {/if}
 {#if generation.status !== 'completed'}<p class="status" data-testid="generation-status" role={generation.status === 'failed' ? 'alert' : 'status'}>{generation.message}</p>{/if}
</section>

<style>
 .answer{border-top:2px solid #294b38;border-bottom:1px solid #cbd1c3;padding:22px 0;margin:30px 0;color:#242f29}.heading{display:flex;align-items:baseline;justify-content:space-between;gap:16px}h2{font:23px Georgia,serif;margin:0}.heading>span{font:10px 'Segoe UI',sans-serif;text-transform:uppercase;letter-spacing:.08em;color:#69725f}.text{white-space:pre-wrap;font:17px/1.8 Georgia,serif;overflow-wrap:anywhere}.status{font:13px/1.7 'Segoe UI',sans-serif;color:#69725f}.insufficient{border-left:3px solid #ae6b34;padding:6px 12px;font:12px/1.6 'Segoe UI',sans-serif;color:#805228}nav{display:flex;flex-wrap:wrap;align-items:baseline;gap:10px 15px;font:11px/1.7 'Segoe UI',sans-serif}nav>span{color:#69725f;text-transform:uppercase;font-size:9px;letter-spacing:.1em}a{text-decoration:underline;text-underline-offset:3px;color:#294b38}.note{font:10px/1.7 'Segoe UI',sans-serif;color:#69725f;margin:18px 0 0}@media(max-width:500px){.heading{align-items:flex-start}.heading>span{max-width:110px;text-align:right;font-size:9px}}
</style>
