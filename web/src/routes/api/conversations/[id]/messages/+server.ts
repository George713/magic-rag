import { forwardStream } from '$lib/server/forward-stream';
import type { RequestHandler } from './$types';
export const POST: RequestHandler = ({request,fetch,params}) => forwardStream(request,fetch,`/api/conversations/${encodeURIComponent(params.id)}/messages`);
