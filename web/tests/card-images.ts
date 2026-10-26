import type {Page} from '@playwright/test';

// Card-proportioned image fixture; opaque corners reproduce source JPEG padding.
export async function installCardImages(page:Page, {opaqueCorners=false} = {}) {
 await page.route('https://cards.test/**',route=>{
  const back=route.request().url().includes('back');
  const name=back?'Insectile Aberration':route.request().url().includes('bolt')?'Lightning Bolt':'Delver of Secrets';
  const artwork=back?'#789174':'#527c93';
  return route.fulfill({contentType:'image/svg+xml',body:`<svg xmlns="http://www.w3.org/2000/svg" width="488" height="680" viewBox="0 0 488 680">
   ${opaqueCorners?'<rect width="488" height="680" fill="white"/>':''}
   <rect width="488" height="680" rx="26" fill="#101211"/>
   <rect x="22" y="22" width="444" height="636" rx="16" fill="#667b7c"/>
   <rect x="34" y="36" width="420" height="52" rx="10" fill="#c8d2c6"/>
   <text x="48" y="70" font-family="Georgia" font-size="24" fill="#17231e">${name}</text>
   <rect x="34" y="100" width="420" height="300" fill="${artwork}"/>
   <circle cx="335" cy="180" r="48" fill="#d4c9a2"/>
   <path d="M34 400L155 190L220 320L305 240L454 400Z" fill="#263c3b"/>
   <rect x="34" y="410" width="420" height="44" rx="8" fill="#c8d2c6"/>
   <text x="48" y="439" font-family="Georgia" font-size="20" fill="#17231e">Creature — browser fixture</text>
   <rect x="34" y="466" width="420" height="160" rx="8" fill="#dddcca"/>
   <text x="50" y="506" font-family="Georgia" font-size="22" fill="#17231e">${back?'Flying':'Discover a card.'}</text>
  </svg>`});
 });
}
