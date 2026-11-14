import type { Card, Generation, Search, Trace } from '$lib/types';

/** Newline-delimited events of one streamed message; `search` repeats once per completed search. */
export type MessageEvent =
 | {event: 'start'; trace: Trace}
 | {event: 'search'; index: number; query: string; card_count: number; top_cards: {card_id: string; name: string}[]; search: Search}
 | {event: 'delta'; text: string}
 | {event: 'done'; generation: Generation; trace: Trace};

export interface MessageRequest {question: string; mode: string; settings: Record<string, number>; filters: unknown}

export function cancelPath(trace: Trace) {
 return `/api/conversations/${encodeURIComponent(trace.conversation_id!)}/turns/${encodeURIComponent(trace.turn_id!)}/cancel`;
}

function combined(searches: Search[]): Card[] {
 const seen = new Set<string>();
 return searches.flatMap(search => search.selected_evidence).filter(card => !seen.has(card.card_id) && !!seen.add(card.card_id));
}

/** The turn as known after one more event; `done` carries the saved turn, which is authoritative. */
export function applyEvent(trace: Trace | null, event: MessageEvent): Trace {
 if (event.event === 'start' || event.event === 'done') return event.trace;
 if (!trace) throw new Error('The message stream did not start with its turn.');
 if (event.event === 'search') {
  const searches = [...trace.searches]; searches[event.index] = event.search;
  return {...trace, searches, selected_evidence: combined(searches)};
 }
 if (event.event === 'delta') return {...trace, generation: {...trace.generation, text: (trace.generation.text || '') + event.text}};
 throw new Error('The message stream returned an unknown event.');
}

function failure(result: unknown) {
 const detail = (result as {detail?: unknown} | null)?.detail;
 return typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((item: {msg: string}) => item.msg).join(' ') : 'Search failed. Check the question and filters.';
}

/** Send one message as one streamed request; `update` receives the turn after every event. */
export async function streamMessage(conversationId: string, body: MessageRequest, update: (trace: Trace) => void, signal: AbortSignal): Promise<Trace> {
 const response = await fetch(`/api/conversations/${encodeURIComponent(conversationId)}/messages`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal});
 if (!response.ok || !response.body) throw new Error(failure(await response.json().catch(() => null)));
 const reader = response.body.getReader();
 const decoder = new TextDecoder();
 let buffered = '';
 let trace: Trace | null = null;
 try {
  while (true) {
   const chunk = await reader.read();
   buffered += decoder.decode(chunk.value,{stream:!chunk.done});
   let boundary: number;
   while ((boundary = buffered.indexOf('\n')) >= 0) {
    const line = buffered.slice(0,boundary); buffered = buffered.slice(boundary+1);
    if (!line.trim()) continue;
    const event = JSON.parse(line) as MessageEvent;
    if (signal.aborted) return trace!;
    trace = applyEvent(trace,event);
    update(trace);
    if (event.event === 'done') return trace;
   }
   if (chunk.done) break;
  }
  throw new Error('The answer connection closed before completion. Partial output is incomplete.');
 } finally {
  await reader.cancel().catch(() => {});
  reader.releaseLock();
 }
}
