import type { ExactFilters } from './filters';
export interface Card {
 card_id: string; name: string; text: string; mana_cost: string; mana_value: number;
 colors: string[]; type_line: string; score: number; rank: number;
 images?: {name: string; url: string}[]; source_url?: string | null;
 signals?: Record<string, {rank:number; score:number}>;
 fused_rank?: number; fusion_score?: number; rank_change?: number;
}
/** One search within a turn: its query, the mode/filters it ran under, stage rankings, timings, and selected cards. */
export interface Search {
 query: string; mode: string; filters: ExactFilters;
 models: Record<string, unknown>; settings: Record<string, unknown>;
 stages: Record<string, Card[]>; selected_evidence: Card[]; timings_ms: Record<string, number>;
}
/** A saved turn's trace; while the turn is in progress, `rewrite` and `answer_context` are null and `searches` grows. */
export interface Trace {
 answer_context?: {retrieval_query: string; conversation_context: {question: string; query: string; answer?: string}[]; context_truncated: boolean} | null;
 conversation_id?: string; turn_id?: string;
 trace_id: string; question: string; corpus: {id: string; metadata: string} | null;
 searches: Search[]; selected_evidence: Card[]; timings_ms: Record<string, number>;
 rewrite: {status: string; message: string; elapsed_ms?: number} | null; generation: Generation;
}
export interface Generation {
 status: string; message: string; text?: string; insufficient_evidence?: boolean;
 citations?: {card_id: string; name: string}[];
 assets?: Card[];
}
