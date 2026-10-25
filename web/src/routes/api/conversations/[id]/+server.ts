import { forward } from '$lib/server/forward';
import type { RequestHandler } from './$types';
export const GET: RequestHandler = event => forward(event,`/api/conversations/${encodeURIComponent(event.params.id)}`);
export const DELETE: RequestHandler = event => forward(event,`/api/conversations/${encodeURIComponent(event.params.id)}`);
export const PATCH: RequestHandler = event => forward(event,`/api/conversations/${encodeURIComponent(event.params.id)}`);
