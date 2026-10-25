import type { Generation, Trace } from '$lib/types';

export function answerPath(trace: Trace, action: 'stream' | 'cancel') {
 return `/api/conversations/${encodeURIComponent(trace.conversation_id!)}/turns/${encodeURIComponent(trace.turn_id!)}/${action}`;
}

export async function streamAnswer(trace: Trace, update: (generation: Generation) => void, signal: AbortSignal) {
 const response = await fetch(answerPath(trace,'stream'), {method:'POST',signal});
 if (!response.ok || !response.body) throw new Error('The answer stream could not start. Check the service connection and submit another question.');
 const reader = response.body.getReader();
 const decoder = new TextDecoder();
 let buffered = '';
 let generation: Generation = {status:'generating',message:'Generating from selected evidence.',text:'',citations:[]};
 let completed = false;
 try {
  while (true) {
   const chunk = await reader.read();
   buffered += decoder.decode(chunk.value,{stream:!chunk.done});
   let boundary: number;
   while ((boundary = buffered.indexOf('\n')) >= 0) {
    const line = buffered.slice(0,boundary); buffered = buffered.slice(boundary+1);
    if (!line.trim()) continue;
    const event = JSON.parse(line);
    if (signal.aborted) return;
    if (event.event === 'delta') generation = {...generation,text:(generation.text || '') + event.text};
    else if (event.event === 'start' || event.event === 'done') generation = event.generation;
    else throw new Error('The answer stream returned an unknown event.');
    update(generation);
    if (event.event === 'done') {completed = true; return;}
   }
   if (chunk.done) break;
  }
  if (!completed) throw new Error('The answer connection closed before completion. Partial output is incomplete.');
 } finally {
  await reader.cancel().catch(() => {});
  reader.releaseLock();
 }
}
