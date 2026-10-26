/** Reveal the cited turn's evidence before the browser follows its fragment link. */
export function revealEvidence(event: MouseEvent) {
 const link = event.currentTarget as HTMLAnchorElement;
 const target = document.getElementById(decodeURIComponent(link.hash.slice(1)));
 const disclosure = target?.closest<HTMLDetailsElement>('details.evidence');
 if (disclosure) disclosure.open = true;
}
