<script lang="ts">
 import type { Card } from '$lib/types';
 let { card, row = false }: {card: Card; row?: boolean} = $props();
 let dialog = $state<HTMLDialogElement>();
 let selected = $state<{name:string; url:string} | null>(null);
 let failed = $state<string[]>([]);
 let opener: HTMLButtonElement | undefined;
 function enlarge(image: {name:string; url:string}, button: HTMLButtonElement) {
  opener = button;
  selected = image;
  dialog?.showModal();
 }
 function close() {
  dialog?.close();
  opener?.focus();
 }
</script>

{#if card.images?.length}
 <div class="card-images" class:row aria-label={`${card.name} images`}>
  {#each card.images as image (image.url)}
   <figure>
    {#if failed.includes(image.url)}
     <p class="unavailable">Image unavailable: {image.name}</p>
    {:else}
     <button type="button" class="preview" aria-label={`Enlarge ${image.name}`} onfocus={(event) => {if (row) event.currentTarget.scrollIntoView({block:'nearest',inline:'nearest'});}} onclick={(event) => enlarge(image, event.currentTarget)}>
      <img src={image.url} alt={image.name} loading="lazy" onerror={() => failed = [...failed, image.url]} />
     </button>
    {/if}
    <figcaption>{image.name}</figcaption>
   </figure>
  {/each}
 </div>
 <dialog bind:this={dialog} aria-label={selected ? `${selected.name} enlarged image` : 'Enlarged card image'} onclick={close} onkeydown={(event) => {if (event.key === 'Escape') {event.preventDefault();close();}}}>
  <div class="enlarged">
   {#if selected}
    <div class="image-frame">
     <img src={selected.url} alt={selected.name} onerror={() => failed = [...failed, selected!.url]} />
     <button type="button" class="close" aria-label="Close image" onclick={close}>×</button>
    </div>
    <p>{selected.name}</p>
   {/if}
  </div>
 </dialog>
{/if}

<style>
 .card-images{display:flex;flex-wrap:wrap;gap:16px;margin:18px 0;max-width:100%}
 figure{margin:0;min-width:0;max-width:min(210px,100%);flex:0 1 210px}
 .row{display:contents}
 .row figure{flex:0 0 210px;max-width:none}
 .row figcaption{text-align:center}
 .preview{display:block;padding:0;background:transparent;border:0;border-radius:10px;cursor:zoom-in;max-width:100%;scroll-margin:6px}
 .preview img{display:block;width:100%;height:auto}
 .preview img,.image-frame>img{border-radius:5.5% / 4%}
 figcaption,.unavailable{font:12px/1.5 'Segoe UI',sans-serif;color:#a5b5ab;overflow-wrap:anywhere;margin:8px 0 0}
 dialog{color:#e9eee9;background:transparent;border:0;padding:20px;margin:0;width:100vw;height:100dvh;max-width:100vw;max-height:100dvh;cursor:zoom-out}
 dialog[open]{display:flex;align-items:center;justify-content:center}
 dialog::backdrop{background:#030806de}
 .enlarged{display:flex;flex-direction:column;align-items:center;gap:12px;max-width:100%;width:min-content}
 .image-frame{position:relative;line-height:0}
 .image-frame>img{display:block;max-height:calc(100dvh - 100px);max-width:calc(100vw - 40px);width:auto;height:auto;object-fit:contain}
 .enlarged>p{font:14px/1.4 'Segoe UI',sans-serif;margin:0;overflow-wrap:anywhere;text-align:center;max-height:40px;overflow:auto;max-width:100%}
 .close{position:absolute;top:8px;right:8px;width:40px;height:40px;cursor:pointer;color:#fff;background:#111b;border:0;border-radius:50%;padding:0;font:26px/1 'Segoe UI',sans-serif}
 .close:hover{background:#111e}
 :focus-visible{outline:3px solid #d1ad65;outline-offset:4px}
</style>
