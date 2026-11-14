import { forwardStream, turnPath } from '$lib/server/forward-stream';
import type { RequestHandler } from './$types';
export const POST: RequestHandler = ({request,fetch,params}) => forwardStream(request,fetch,turnPath(params.id,params.turn,'cancel'));
