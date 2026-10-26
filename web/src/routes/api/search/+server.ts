import { env } from '$env/dynamic/private';
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ request, fetch }) => {
 try {
  const upstream = await fetch(`${env.MAGIC_RAG_API || 'http://127.0.0.1:8000'}/api/search`, {
   method: 'POST', headers: {'Content-Type': 'application/json'}, body: await request.text(),
   signal: request.signal
  });
  return new Response(upstream.body, { status: upstream.status, headers: {'Content-Type': 'application/json'} });
 } catch {
  return json({detail: 'The local retrieval service is unavailable. Start the Python service and try again.'}, {status: 502});
 }
};
