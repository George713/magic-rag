<script lang="ts">
 import type {Search} from '$lib/types';
 let {searches}:{searches:Search[]}=$props();
 const cards=(count:number)=>`${count} ${count===1?'card':'cards'}`;
</script>
{#if searches.length}
 <ol class="searches" aria-label="Searches">
  {#each searches as search}<li><span class="query">searching "{search.query}"</span> · <span class="count">{cards(search.selected_evidence.length)}</span></li>{/each}
 </ol>
{/if}
<style>
 .searches{list-style:none;margin:10px 0 0;padding:0;display:grid;gap:4px;font:12px/1.6 'Segoe UI',sans-serif;color:#9aa99b;min-width:0}.query{color:#c7d4c2;overflow-wrap:anywhere}.count{white-space:nowrap}
</style>
