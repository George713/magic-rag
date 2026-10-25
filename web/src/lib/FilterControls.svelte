<script lang="ts">
 import { cardTypes, colorNames, describeFilters, type ExactFilters } from '$lib/filters';
 export let filters: ExactFilters = {};
 export let disabled = false;
 function color(code: string, selected: boolean) {
  const colors = filters.colors || [];
  filters = {...filters, colors:selected ? [...colors,code] : colors.filter(c => c !== code)};
 }
 function type(name: string, selected: boolean) {
  const types = filters.card_types || [];
  filters = {...filters,card_types:selected ? [...types,name] : types.filter(t => t !== name)};
 }
 function bound(name: 'mana_value_min' | 'mana_value_max', input: HTMLInputElement) {
  filters = {...filters,[name]:input.value === '' ? null : input.valueAsNumber};
 }
</script>

<fieldset {disabled}>
 <legend>Exact filters</legend>
 <div class="filter-heading"><p data-testid="active-filters">{describeFilters(filters)}</p><button type="button" onclick={() => {filters={};}}>Clear filters</button></div>
 <div class="group-title">Card colors</div>
 <div class="options">
  <label><input type="radio" name="color-scope" checked={filters.colors == null} onchange={() => {filters={...filters,colors:null};}}/> Any colors</label>
  <label><input type="radio" name="color-scope" checked={filters.colors != null && filters.colors.length === 0} onchange={() => {filters={...filters,colors:[]};}}/> Colorless</label>
  {#each Object.entries(colorNames) as [code,name]}
   <label><input type="checkbox" checked={filters.colors?.includes(code) || false} onchange={event => color(code,event.currentTarget.checked)}/>{name}</label>
  {/each}
 </div>
 <p class="hint">Selected colors match exactly, including multicolor cards. These are card colors, not color identity.</p>
 <div class="group-title">Card types <span>All selected types must match</span></div>
 <div class="types">
  {#each cardTypes as name}<label><input type="checkbox" checked={filters.card_types?.includes(name) || false} onchange={event => type(name,event.currentTarget.checked)}/>{name}</label>{/each}
 </div>
 <div class="bounds">
  <label>Minimum mana value<input type="number" min="0" step="any" value={filters.mana_value_min ?? ''} oninput={event => bound('mana_value_min',event.currentTarget)} placeholder="Any"/></label>
  <label>Maximum mana value<input type="number" min="0" step="any" value={filters.mana_value_max ?? ''} oninput={event => bound('mana_value_max',event.currentTarget)} placeholder="Any"/></label>
 </div>
 <p class="hint">Mana boundaries include the entered values. Clear filters to include every card.</p>
</fieldset>

<style>
 fieldset{border:1px solid #cbd1c3;padding:15px 16px;margin:18px 0;min-width:0;background:#f1f2e9}legend{font:14px Georgia,serif;padding:0 7px;color:#344a39}.filter-heading{display:flex;justify-content:space-between;align-items:baseline;gap:12px}.filter-heading p{font-size:11px;line-height:1.6;color:#475e45;margin:0;overflow-wrap:anywhere}.filter-heading button{font:11px 'Segoe UI',sans-serif;color:#294b38;background:transparent;border:0;text-decoration:underline;text-underline-offset:3px;cursor:pointer;white-space:nowrap;padding:4px 0}.group-title{font-size:11px;font-weight:600;margin:18px 0 9px}.group-title span{font-size:10px;font-weight:400;color:#66725f;margin-left:8px}.options{display:flex;gap:11px 16px;flex-wrap:wrap}.options label,.types label{font-size:11px;display:flex;align-items:center;gap:5px;min-height:25px}.types{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:3px 10px}.hint{font-size:10px;line-height:1.7;color:#68725f;margin:10px 0 0}input{accent-color:#294b38}input[type=checkbox],input[type=radio]{margin:0;width:14px;height:14px;flex-shrink:0}.bounds{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:18px}.bounds label{font-size:11px;font-weight:600}.bounds input{display:block;width:100%;margin-top:7px;padding:9px;border:1px solid #aab5a5;border-radius:2px;background:#fffefa;color:#243e30;font:12px 'Segoe UI',sans-serif}@media(max-width:480px){fieldset{padding:12px}.types{grid-template-columns:repeat(2,minmax(0,1fr))}.group-title span{display:block;margin:5px 0 0}.options{gap:8px 12px}.bounds{gap:12px}.bounds label{font-size:10px}}
</style>
