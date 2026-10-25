import { env } from '$env/dynamic/private';
import { json } from '@sveltejs/kit';

export async function GET({ fetch }) {
 try {
  const response = await fetch(`${env.MAGIC_RAG_API || 'http://127.0.0.1:8000'}/api/provider`);
  return new Response(response.body, {status:response.status, headers:{'Content-Type':'application/json'}});
 } catch {
  return json({status:'unavailable',message:'The local retrieval service is unavailable. Start the Python service and try again.'},{status:503});
 }
}
