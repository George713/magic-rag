import {expandEvidence} from './evidence';
import {test,expect,type Page} from '@playwright/test';
const pixel=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jC34AAAAASUVORK5CYII=','base64');
test.beforeEach(async({page,request})=>{
 for(const chat of await(await request.get('/api/conversations')).json())await request.delete(`/api/conversations/${chat.id}`);
 await page.route('https://cards.test/**',route=>route.fulfill({contentType:'image/png',body:pixel}));
});
async function send(page:Page,question:string){await page.getByLabel('Your question').fill(question);await page.getByRole('button',{name:'Send',exact:true}).click();}
test('automatic streaming, copy, followups and turn-specific citations survive reopening',async({page})=>{
 await page.goto('/');await send(page,'Delver');
 await expect(page.getByTestId('answer-text')).toHaveText('The transformed face has flying.');
 await page.getByRole('button',{name:'Copy answer',exact:true}).click();
 await expect.poll(()=>page.evaluate(()=>navigator.clipboard.readText())).toBe('The transformed face has flying.');
 await send(page,'Show those again');await expect(page.getByTestId('answer-text')).toHaveCount(2);
 const last=page.locator('.turn').last();await last.getByText('Retrieval details',{exact:true}).click();
 await expect(last.getByTestId('actual-query')).toHaveText('Delver');
 const links=page.getByTestId('answer-citations').getByRole('link');
 expect(await links.nth(0).getAttribute('href')).not.toBe(await links.nth(1).getAttribute('href'));
 await expect(page.locator('details.evidence').first()).not.toHaveAttribute('open','');
 await expect(page.locator('details.evidence').last()).not.toHaveAttribute('open','');
 await links.nth(0).click();const target=await links.nth(0).getAttribute('href');await expect(page.locator(target!)).toContainText('Flying');
 await expect(page.locator(target!)).toBeInViewport();
 await expect(page.locator('details.evidence').first()).toHaveAttribute('open','');
 await expect(page.locator('details.evidence').last()).not.toHaveAttribute('open','');
 await page.reload();await expect(page.getByTestId('answer-text')).toHaveCount(2);
});
test('assets-only and combined responses display separate source images and both faces reopen',async({page})=>{
 await page.goto('/');await send(page,'Delver assets only');
 const assets=page.getByRole('region',{name:'Card assets',exact:true});await expect(assets).toBeVisible();
 await expect(page.getByTestId('answer-text')).toHaveCount(0);await expect(page.getByRole('button',{name:'Copy answer'})).toHaveCount(0);
 await expect(assets.getByRole('img')).toHaveCount(2);await expect(page.locator('details.evidence')).not.toHaveAttribute('open','');
 await assets.getByRole('button',{name:'Enlarge Insectile Aberration',exact:true}).click();
 await expect(page.getByRole('dialog')).toBeVisible();await page.getByRole('button',{name:'Close image'}).click();await expect(page.getByRole('dialog')).not.toBeVisible();
 await page.reload();await expect(assets.getByRole('img')).toHaveCount(2);await expect(page.locator('details.evidence')).not.toHaveAttribute('open','');
 await assets.getByRole('link').click();await expect(page.locator('details.evidence')).toHaveAttribute('open','');
 await send(page,'Delver assets');const last=page.locator('.turn').last();await expect(last.getByTestId('answer-text')).toBeVisible();await expect(last.getByRole('region',{name:'Card assets'})).toBeVisible();
});
test('failed images keep selected asset names and evidence readable',async({page})=>{
 await page.unroute('https://cards.test/**');await page.route('https://cards.test/**',route=>route.abort());
 await page.goto('/');await send(page,'Delver assets only');
 await expect(page.getByRole('region',{name:'Card assets'}).getByText('Image unavailable: Delver of Secrets')).toBeVisible();
 await expandEvidence(page);await expect(page.locator('.card-text')).toContainText('Flying');
 await page.getByText('Retrieval details',{exact:true}).click();await expect(page.getByTestId('actual-query')).toHaveText('Delver assets only');
});
test('Stop and provider failure retain incomplete output and permit subsequent turns',async({page})=>{
 await page.goto('/');await send(page,'Delver stop');await expect(page.getByTestId('answer-text')).toHaveText('The transformed ');
 await page.getByRole('button',{name:'Stop answer'}).click();await expect(page.getByTestId('generation-status')).toContainText('stopped');
 await send(page,'Delver fail');await expect(page.locator('.turn').last().getByTestId('generation-status')).toContainText('failed');
 await expandEvidence(page);await expect(page.locator('.turn').last().locator('.card-text')).toContainText('Flying');
 await page.reload();await expect(page.getByTestId('answer-text')).toHaveCount(2);
});
test('ordinary source image and legacy asset without imagery remain usable',async({page})=>{
 await page.goto('/');await send(page,'Lightning Bolt assets only');
 await expect(page.getByRole('region',{name:'Card assets'}).getByRole('img')).toHaveCount(1);
 await page.getByRole('region',{name:'Card assets'}).getByRole('button',{name:'Enlarge Lightning Bolt',exact:true}).click();
 await page.getByRole('button',{name:'Close image',exact:true}).click();
 await send(page,'Sol Ring assets only');
 const assets=page.locator('.turn').last().getByRole('region',{name:'Card assets'});
 await expect(assets.getByRole('link',{name:'Sol Ring',exact:true})).toBeVisible();
 await expect(assets.getByRole('img')).toHaveCount(0);
 await page.reload();await expect(page.locator('.turn').last().getByRole('region',{name:'Card assets'}).getByRole('link',{name:'Sol Ring',exact:true})).toBeVisible();
});
