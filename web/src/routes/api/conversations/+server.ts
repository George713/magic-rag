import { forward } from '$lib/server/forward';
import type { RequestHandler } from './$types';
export const GET: RequestHandler = event => forward(event,'/api/conversations');
export const POST: RequestHandler = event => forward(event,'/api/conversations');
