export interface ExactFilters {
 colors?: string[] | null;
 card_types?: string[];
 legendary?: boolean;
 mana_value_min?: number | null;
 mana_value_max?: number | null;
}
export const colorNames: Record<string,string> = {W:'White',U:'Blue',B:'Black',R:'Red',G:'Green'};
export const cardTypes = ['Artifact','Battle','Conspiracy','Creature','Dungeon','Enchantment','Instant','Kindred','Land','Phenomenon','Plane','Planeswalker','Scheme','Sorcery','Vanguard'];
export function describeFilters(filters: ExactFilters): string {
 const parts: string[] = [];
 if (filters.colors != null) parts.push(filters.colors.length ? `Exact colors: ${filters.colors.map(c => colorNames[c] || c).join(', ')}` : 'Colorless');
 if (filters.card_types?.length) parts.push(filters.card_types.join(' + '));
 if (filters.legendary) parts.push('Legendary only');
 if (filters.mana_value_min != null) parts.push(`Mana ≥ ${filters.mana_value_min}`);
 if (filters.mana_value_max != null) parts.push(`Mana ≤ ${filters.mana_value_max}`);
 return parts.join(' · ') || 'Any cards';
}
