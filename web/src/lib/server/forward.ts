import { env } from '$env/dynamic/private';
import { json, type RequestEvent } from '@sveltejs/kit';

export async function forward(event: RequestEvent, path: string) {
 try {
  const response = await event.fetch(`${env.MAGIC_RAG_API || 'http://127.0.0.1:8000'}${path}`, {
   method:event.request.method,
   headers:{'Content-Type':'application/json'},
   body:['GET','DELETE'].includes(event.request.method) ? undefined : await event.request.text(),
   signal:event.request.signal
  });
  return new Response(response.body,{status:response.status,headers:{'Content-Type':'application/json'}});
 } catch {
  return json({detail:'The local service is unavailable. Start the Python service and try again.'},{status:502});
 }
}
