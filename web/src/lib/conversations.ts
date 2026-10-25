import type { Trace } from './types';

export interface SavedTurn {
 id: string; conversation_id: string; question: string; state: string;
 trace: Trace; answer: string | null; error: string | null; created_at: string;
}
export interface ConversationSummary {
 id: string; title: string; created_at: string; updated_at: string;
}
export interface Conversation extends ConversationSummary { turns: SavedTurn[] }
