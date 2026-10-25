<script lang="ts">
 import type { Card } from '$lib/types';
 let { card }: {card: Card} = $props();
 let dialog: HTMLDialogElement;
 let selected = $state<{name:string; url:string} | null>(null);
 let failed = $state<string[]>([]);
 function enlarge(image: {name:string; url:string}) {
  selected = image;
  dialog.showModal();
 }
</script>

{#if card.images?.length}
 <div class="card-images" aria-label={`${card.name} images`}>
  {#each card.images as image}
   <figure>
    {#if failed.includes(image.url)}
     <p class="unavailable">Image unavailable: {image.name}</p>
    {:else}
     <button type="button" class="preview" aria-label={`Enlarge ${image.name}`} onclick={() => enlarge(image)}>
      <img src={image.url} alt={image.name} loading="lazy" onerror={() => failed = [...failed, image.url]} />
     </button>
    {/if}
    <figcaption>{image.name}</figcaption>
   </figure>
  {/each}
 </div>
 <dialog bind:this={dialog} aria-label={selected ? `${selected.name} enlarged image` : 'Enlarged card image'}>
  <div class="enlarged">
   <button type="button" class="close" onclick={() => dialog.close()}>Close image</button>
   {#if selected}
    <img src={selected.url} alt={selected.name} onerror={() => failed = [...failed, selected!.url]} />
    <p>{selected.name}</p>
   {/if}
  </div>
 </dialog>
{/if}

<style>
 .card-images{display:flex;flex-wrap:wrap;gap:16px;margin:18px 0;max-width:100%}
 figure{margin:0;min-width:0;max-width:min(210px,100%);flex:0 1 210px}
 .preview{display:block;padding:0;background:transparent;border:0;border-radius:10px;cursor:zoom-in;max-width:100%}
 .preview img{display:block;width:100%;height:auto;border-radius:10px}
 figcaption,.unavailable{font:12px/1.5 'Segoe UI',sans-serif;color:#a5b5ab;overflow-wrap:anywhere;margin:8px 0 0}
 dialog{color:#e9eee9;background:#17231e;border:1px solid #485e50;border-radius:14px;padding:18px;max-width:calc(100vw - 32px);max-height:calc(100dvh - 32px)}
 dialog::backdrop{background:#030806de}
 .enlarged{display:flex;flex-direction:column;align-items:center;gap:12px;max-width:100%}
 .enlarged>img{display:block;max-height:calc(100dvh - 160px);max-width:100%;width:auto;object-fit:contain;border-radius:12px}
 .enlarged>p{font:14px/1.4 'Segoe UI',sans-serif;margin:0;overflow-wrap:anywhere}
 .close{align-self:flex-end;cursor:pointer;color:#edf3ee;background:#334b3e;border:1px solid #637e69;border-radius:5px;padding:9px 14px;font:13px 'Segoe UI',sans-serif}
 :focus-visible{outline:3px solid #d1ad65;outline-offset:4px}
</style>
