import { env } from '$env/dynamic/private';
import { json } from '@sveltejs/kit';

export async function forwardAnswer(request: Request, fetcher: typeof fetch, conversation: string, turn: string, action: 'stream' | 'cancel') {
 try {
  const upstream = await fetcher(`${env.MAGIC_RAG_API || 'http://127.0.0.1:8000'}/api/conversations/${encodeURIComponent(conversation)}/turns/${encodeURIComponent(turn)}/${action}`, {method:'POST',signal:request.signal});
  return new Response(upstream.body,{status:upstream.status,headers:{'Content-Type':upstream.headers.get('Content-Type') || 'application/json','Cache-Control':'no-store','X-Accel-Buffering':'no'}});
 } catch {
  return json({detail:'The answer service connection failed. Retrieved evidence is preserved.'},{status:502});
 }
}
