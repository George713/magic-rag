<script lang="ts">
 import { onMount } from 'svelte';
 import type { Conversation, ConversationSummary } from '$lib/conversations';
 import type { Trace } from '$lib/types';
 export let conversationId: string | null = null;
 export let busy = false;
 export let onselect: (trace: Trace | null) => void;
 let conversations: ConversationSummary[] = [];
 let current: Conversation | null = null;
 let selectedTurn: string | null = null;
 let loading = false;
 let error = '';

 async function call(path: string, method='GET') {
  const response = await fetch(`/api/conversations${path}`, {method});
  if (!response.ok) {
   const result = await response.json();
   throw new Error(typeof result.detail === 'string' ? result.detail : 'Conversation could not be loaded. Try again.');
  }
  return response.status === 204 ? null : response.json();
 }
 async function refresh() { conversations = await call(''); }
 async function create() {
  current = await call('', 'POST');
  conversationId = current!.id;
  selectedTurn = null;
  await refresh();
  return conversationId;
 }
 export async function ensureConversation(): Promise<string> {
  return conversationId || await create();
 }
 export async function saved(trace: Trace) {
  if (!conversationId) return;
  current = await call(`/${conversationId}`);
  selectedTurn = trace.turn_id || null;
  await refresh();
 }
 async function action(run: () => Promise<void>) {
  loading = true; error = '';
  try { await run(); }
  catch(e) { error = e instanceof Error ? e.message : 'Conversation request failed. Try again.'; }
  finally { loading = false; }
 }
 async function open(id: string) {
  current = await call(`/${id}`);
  conversationId = id;
  const latest = current!.turns.at(-1);
  selectedTurn = latest?.id || null;
  onselect(latest?.trace || null);
 }
 async function remove(id: string) {
  await call(`/${id}`, 'DELETE');
  if (conversationId === id) {
   conversationId = null; current = null; selectedTurn = null; onselect(null);
  }
  await refresh();
 }
 function stateLabel(state: string) {
  return ({retrieval_complete:'Retrieval complete',completed:'Completed',cancelled:'Cancelled',failed:'Failed',generating:'Generating'} as Record<string,string>)[state] || state;
 }
 onMount(() => { void action(refresh); });
</script>

<section aria-label="Conversations" aria-busy={loading}>
 <div class="history-heading"><h2>Saved conversations</h2><button class="new" disabled={busy || loading} onclick={() => action(async () => {await create(); onselect(null);})}>New conversation <span aria-hidden="true">+</span></button></div>
 {#if error}<p class="error" role="alert">{error}</p>{/if}
 <div class="conversation-list">
  {#each conversations as conversation}
   <div class:active={conversationId === conversation.id} class="conversation">
    <button class="open" aria-label={`Open conversation: ${conversation.title}`} aria-pressed={conversationId === conversation.id} disabled={busy || loading} onclick={() => action(() => open(conversation.id))}>{conversation.title}</button>
    <button class="delete" aria-label={`Delete conversation: ${conversation.title}`} disabled={busy || loading} onclick={() => action(() => remove(conversation.id))}>×</button>
   </div>
  {:else}<p class="empty">Your first search starts a saved conversation.</p>{/each}
 </div>
 {#if current && current.turns.length}
  <ol aria-label="Conversation turns">
   {#each current.turns as turn, i}
    <li><button class:selected={selectedTurn === turn.id} aria-label={`View turn ${i+1}: ${turn.question}`} aria-pressed={selectedTurn === turn.id} disabled={busy || loading} onclick={() => {selectedTurn=turn.id; onselect(turn.trace);}}><span class="number">{String(i+1).padStart(2,'0')}</span><span class="question">{turn.question}</span><span class="state">{stateLabel(turn.state)}</span></button></li>
   {/each}
  </ol>
 {/if}
</section>

<style>
 section{margin:0 0 32px;padding:18px 0;border-top:1px solid #cbd1c3;border-bottom:1px solid #cbd1c3;min-width:0}.history-heading{display:flex;align-items:center;justify-content:space-between;gap:16px}h2{font:17px Georgia,serif;margin:0}button{font:inherit;cursor:pointer;border:0;border-radius:2px}button:disabled{opacity:.5;cursor:default}.new{font-size:11px;background:transparent;color:#294b38;padding:7px 0;white-space:nowrap}.new span{margin-left:10px}.conversation-list{display:flex;gap:8px;flex-wrap:wrap;max-height:170px;overflow:auto;margin-top:12px}.conversation{display:flex;align-items:stretch;border:1px solid #d2d8ca;border-radius:2px;background:#fffefa;min-width:0;max-width:100%}.conversation.active{border-color:#54705a;background:#e6eddf}.open{background:transparent;color:#344a39;padding:9px 10px;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;max-width:280px}.delete{background:transparent;color:#7c5144;padding:4px 10px;font-size:18px;border-left:1px solid #d2d8ca}.delete:hover{background:#f4ded4}.open:hover{background:#dfe8d7}.empty{font-size:11px;line-height:1.6;color:#697063;margin:0}ol{padding:12px 0 0;margin:0;list-style:none}li+li{margin-top:5px}li button{width:100%;display:flex;align-items:baseline;gap:10px;padding:10px;text-align:left;background:transparent;color:#52634f;font-size:12px}li button:hover,li button.selected{background:#e8ecdf}.number{font:10px Consolas,monospace;color:#7b856f}.question{overflow-wrap:anywhere}.state{margin-left:auto;font-size:10px;white-space:nowrap;color:#697063}.error{font-size:12px;color:#9a392c}@media(max-width:550px){.history-heading{gap:10px}.state{white-space:normal;min-width:55px;text-align:right}.open{max-width:240px}h2{font-size:16px}}
</style>

