export interface Card {
 card_id: string; name: string; text: string; mana_cost: string; mana_value: number;
 colors: string[]; type_line: string; score: number; rank: number;
 signals?: Record<string, {rank:number; score:number}>;
}
export interface Trace {
 conversation_id?: string; turn_id?: string;
 trace_id: string; question: string; query: string; mode: string;
 filters: Record<string, unknown>; corpus: {id: string; metadata: string} | null;
 models: Record<string, unknown>; settings: Record<string, unknown>;
 stages: Record<string, Card[]>; selected_evidence: Card[]; timings_ms: Record<string, number>;
 rewrite: {status: string; message: string}; generation: Generation;
}
export interface Generation {
 status: string; message: string; text?: string; insufficient_evidence?: boolean;
 citations?: {card_id: string; name: string}[];
}
