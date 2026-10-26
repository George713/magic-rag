<script lang="ts">
 import type {Generation} from '$lib/types';
 import CardImages from '$lib/CardImages.svelte';
 let {generation,prefix=''}:{generation:Generation;prefix?:string}=$props();
 let copied=$state(false);let copyError=$state('');
 async function copy(){try{await navigator.clipboard.writeText(generation.text||'');copied=true;copyError='';}catch{copyError='The answer could not be copied. Select its text to copy it.';}}
</script>
<section class="answer" aria-label="Card explanation" aria-live="polite">
 <div class="heading"><h2>Card explanation</h2><span>{generation.status==='completed'?'Evidence grounded':generation.status.replaceAll('_',' ')}</span></div>
 {#if generation.text}
  {#if generation.insufficient_evidence}<p class="insufficient">The selected evidence is insufficient to establish an answer.</p>{/if}
  <p class="text" data-testid="answer-text">{generation.text}</p>
  {#if generation.status==='completed' && generation.citations?.length}<nav aria-label="Answer citations" data-testid="answer-citations"><span>Sources</span>{#each generation.citations as citation}<a href={`#${prefix}-card-${citation.card_id}`}>{citation.name} ↗</a>{/each}</nav>{/if}
  <button class="copy" onclick={copy}>{copied?'Copied':'Copy answer'}</button>{#if copyError}<p role="alert">{copyError}</p>{/if}
 {/if}
 {#if generation.status==='completed' && generation.assets?.length}<section class="assets" aria-label="Card assets">{#each generation.assets as card}<div><a href={`#${prefix}-card-${card.card_id}`}>{card.name}</a><CardImages {card}/></div>{/each}</section>{/if}
 {#if generation.status!=='completed'}<p class="status" data-testid="generation-status" role={generation.status==='failed'?'alert':'status'}>{generation.message}</p>{/if}
</section>
<style>
 .answer{padding:12px 0 20px;min-width:0}.heading{display:flex;align-items:baseline;justify-content:space-between;gap:16px}h2{font:19px Georgia,serif;margin:0;color:#e3e9df}.heading>span{font:9px 'Segoe UI',sans-serif;text-transform:uppercase;letter-spacing:.08em;color:#9aa99b}.text{white-space:pre-wrap;font:16px/1.9 Georgia,serif;color:#e3e9df;overflow-wrap:anywhere}.status{font:13px/1.7 'Segoe UI',sans-serif;color:#a6b6a3}.insufficient{border-left:2px solid #d6bd91;padding:6px 12px;font-size:12px;line-height:1.6;color:#d6bd91}nav{display:flex;flex-wrap:wrap;align-items:baseline;gap:10px 15px;font:11px/1.7 'Segoe UI',sans-serif}nav>span{color:#9aa99b;text-transform:uppercase;font-size:9px;letter-spacing:.1em}a{color:#b4d49d;text-underline-offset:3px}.copy{margin-top:14px;padding:7px 10px;background:transparent;color:#b6c5b0;border:1px solid #465249;border-radius:5px;cursor:pointer;font-size:10px}.copy:hover{background:#2a342d}.assets{display:flex;flex-wrap:wrap;gap:16px;margin:20px 0}p[role=alert]{font-size:12px;color:#f1bcb2}@media(max-width:500px){.heading{align-items:flex-start}.heading>span{max-width:110px;text-align:right;font-size:8px}}
</style>
