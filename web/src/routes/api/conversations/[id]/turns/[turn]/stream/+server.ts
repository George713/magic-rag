import { forwardAnswer } from '$lib/server/forward-answer';
import type { RequestHandler } from './$types';
export const POST: RequestHandler = ({request,fetch,params}) => forwardAnswer(request,fetch,params.id,params.turn,'stream');
