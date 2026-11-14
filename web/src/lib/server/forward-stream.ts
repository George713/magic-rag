import { env } from '$env/dynamic/private';
import { json } from '@sveltejs/kit';

/** Forward a streamed conversation request without buffering; closing the browser request closes upstream. */
export async function forwardStream(request: Request, fetcher: typeof fetch, path: string) {
 try {
  const body = request.method === 'POST' ? await request.text() : undefined;
  const upstream = await fetcher(`${env.MAGIC_RAG_API || 'http://127.0.0.1:8000'}${path}`, {method:'POST',headers:body ? {'Content-Type':'application/json'} : undefined,body:body || undefined,signal:request.signal});
  return new Response(upstream.body,{status:upstream.status,headers:{'Content-Type':upstream.headers.get('Content-Type') || 'application/json','Cache-Control':'no-store','X-Accel-Buffering':'no'}});
 } catch {
  return json({detail:'The answer service connection failed. Start the Python service and try again.'},{status:502});
 }
}

export function turnPath(conversation: string, turn: string, action: 'cancel') {
 return `/api/conversations/${encodeURIComponent(conversation)}/turns/${encodeURIComponent(turn)}/${action}`;
}
