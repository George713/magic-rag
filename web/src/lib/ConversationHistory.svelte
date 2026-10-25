<script lang="ts">
 import { onMount } from 'svelte';
 import type { Conversation, ConversationSummary } from '$lib/conversations';
 import type { ExactFilters } from '$lib/filters';
 import type { Trace } from '$lib/types';
 export let conversationId: string | null = null;
 export let busy = false;
 export let onselect: (conversation: Conversation | null) => void;
 let conversations: ConversationSummary[] = [];
 let loading = false;
 let error = '';
 let pending: Promise<void> = Promise.resolve();
 async function call(path: string, method='GET', body?: unknown) {
  const response = await fetch(`/api/conversations${path}`, {method,headers:body ? {'Content-Type':'application/json'} : undefined,body:body ? JSON.stringify(body) : undefined});
  if (!response.ok) {const result=await response.json(); throw new Error(typeof result.detail === 'string' ? result.detail : 'Conversation could not be saved. Check your filters and try again.');}
  return response.status === 204 ? null : response.json();
 }
 async function refresh() {conversations=await call('');}
 function remember() {if (conversationId) localStorage.setItem('magic-rag-conversation',conversationId); else localStorage.removeItem('magic-rag-conversation');}
 async function create() {const current:Conversation=await call('','POST'); conversationId=current.id; remember(); await refresh(); return current;}
 export async function ensureConversation(): Promise<string> {return conversationId || (await create()).id;}
 export function persistFilters(filters: ExactFilters) {
  const snapshot=structuredClone(filters);
  pending=pending.catch(() => {}).then(async () => {const id=await ensureConversation(); await call(`/${id}`,'PATCH',{filters:snapshot});});
  void pending.catch(e => {error=e.message;});
  return pending;
 }
 export async function flush() {await pending;}
 export async function saved(trace:Trace) {
  const id=trace.conversation_id;
  if (!id || id !== conversationId) return;
  await refresh();
 }
 async function action(run:() => Promise<void>) {loading=true;error='';try {await flush(); await run();} catch(e) {error=e instanceof Error ? e.message : 'Conversation request failed.';}finally{loading=false;}}
 async function open(id:string) {const current=await call(`/${id}`);conversationId=id;remember();onselect(current);}
 async function remove(id:string) {await call(`/${id}`,'DELETE');if(conversationId===id){conversationId=null;remember();onselect(null);}await refresh();}
 onMount(() => {void action(async () => {await refresh();const id=localStorage.getItem('magic-rag-conversation');if(id && conversations.some(c => c.id===id)) await open(id);});});
</script>
<section aria-label="Conversations" aria-busy={loading}>
 <button class="new" disabled={busy || loading} onclick={() => action(async () => {onselect(await create());})}>New chat <span aria-hidden="true">+</span></button>
 <h2>Previous chats</h2>
 {#if error}<p role="alert">{error}</p>{/if}
 <div class="conversation-list">
 {#each conversations as conversation}
  <div class="conversation" class:active={conversationId===conversation.id}>
   <button class="open" aria-label={`Open conversation: ${conversation.title}`} aria-pressed={conversationId===conversation.id} disabled={busy || loading} onclick={() => action(() => open(conversation.id))}>{conversation.title}</button>
   <button class="delete" aria-label={`Delete conversation: ${conversation.title}`} disabled={busy || loading} onclick={() => action(() => remove(conversation.id))}>×</button>
  </div>
 {:else}<p class="empty">Your conversations will appear here.</p>{/each}
 </div>
</section>
<style>
 section{min-width:0}h2{font-size:10px;text-transform:uppercase;letter-spacing:.14em;color:#9aa99b;margin:30px 10px 12px}button{font:inherit;border:0;cursor:pointer;color:inherit}button:disabled{opacity:.45;cursor:default}.new{width:100%;display:flex;justify-content:space-between;padding:13px 14px;background:#28352b;border:1px solid #415143;border-radius:8px;color:#e3e9df;font-size:13px}.new:hover{background:#354738}.conversation-list{display:grid;gap:5px}.conversation{display:flex;border-radius:6px;min-width:0}.conversation.active,.conversation:hover{background:#253027}.open{text-align:left;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:12px 10px;background:transparent;font-size:12px}.delete{padding:8px 10px;background:transparent;color:#9aa99b;font-size:20px}.delete:hover{color:#f1bcb2}.empty,p[role=alert]{font-size:12px;line-height:1.7;color:#9aa99b;padding:0 10px}p[role=alert]{color:#f1bcb2}
</style>
