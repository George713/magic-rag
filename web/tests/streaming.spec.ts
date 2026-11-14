import {expandEvidence} from './evidence';
import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';

test.beforeEach(async ({request}) => {
 const response = await request.get('/api/conversations');
 for (const conversation of await response.json()) await request.delete(`/api/conversations/${conversation.id}`);
});

async function ask(page: Page, question: string) {
 await page.goto('/');
 await page.getByLabel('Your question').fill(question);
 await page.getByRole('button',{name:'Send',exact:true}).click();
}

test('one request shows a live search line, then streams the answer, and reopening shows both', async ({page}) => {
 const messages: string[] = [];
 page.on('request', request => {if (request.url().includes('/api/')) messages.push(`${request.method()} ${new URL(request.url()).pathname}`);});
 await ask(page,'Delver');
 const turn = page.locator('.turn').last();
 const line = turn.getByRole('list',{name:'Searches'}).getByRole('listitem');
 await expect(turn.getByTestId('answer-text')).toHaveText('The transformed ');
 // The search line is already shown while the answer is still streaming.
 await expect(line).toHaveText(['searching "Delver" · 1 card']);
 await expect(page.getByRole('button',{name:'Stop answer'})).toBeVisible();
 await expect(turn.getByTestId('answer-text')).toHaveText('The transformed face has flying.');
 await expect(page.getByRole('button',{name:'Stop answer'})).not.toBeVisible();
 const sent = messages.filter(message => /\/(messages|stream|search)$/.test(message));
 expect(sent).toEqual([expect.stringMatching(/^POST \/api\/conversations\/[^/]+\/messages$/)]);
 await expect(page.getByRole('navigation',{name:'Answer citations'})).toHaveCount(0);
 await expandEvidence(page);await expect(page.locator('article[id$="-card-sample-delver"]')).toContainText('Flying');
 await page.reload();
 await page.getByRole('button',{name:'Open conversation: Delver',exact:true}).click();
 await expect(page.getByRole('list',{name:'Searches'}).getByRole('listitem')).toHaveText(['searching "Delver" · 1 card']);
 await expect(page.getByTestId('answer-text')).toHaveText('The transformed face has flying.');
 await expect(page.locator('.answer .heading')).toContainText('Evidence grounded');
});

test('the search line appears before any answer text and Stop is available while waiting', async ({page}) => {
 await ask(page,'Delver slow');
 const turn = page.locator('.turn').last();
 await expect(turn.getByRole('list',{name:'Searches'}).getByRole('listitem')).toHaveText(['searching "Delver slow" · 1 card']);
 await expect(turn.getByTestId('answer-text')).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Stop answer'})).toBeVisible();
 await expect(turn.getByTestId('answer-text')).toHaveText('The transformed face has flying.');
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('Stop preserves incomplete output and reopening shows cancelled state', async ({page}) => {
 await ask(page,'Delver stop');
 await expect(page.getByTestId('answer-text')).toHaveText('The transformed ');
 await page.getByRole('button',{name:'Stop answer'}).click();
 await expect(page.getByLabel('Your question')).toBeEditable();
 await expect(page.getByTestId('generation-status')).toContainText('stopped');
 await expect(page.getByTestId('answer-text')).toHaveText('The transformed ');
 await page.reload();
 await page.getByRole('button',{name:'Open conversation: Delver stop',exact:true}).click();
 await expect(page.locator('.answer .heading')).toContainText('cancelled');
 await expect(page.getByTestId('generation-status')).toContainText('incomplete');
 await expect(page.getByTestId('answer-text')).toHaveText('The transformed ');
 await expect(page.getByRole('navigation',{name:'Answer citations'})).toHaveCount(0);
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
 await page.screenshot({path:'test-results/stopped-mobile.png',fullPage:true});
});

test('provider failure keeps partial output, source cards, and subsequent turns usable', async ({page}) => {
 await ask(page,'Delver fail');
 await expect(page.getByTestId('answer-text')).toHaveText('The transformed ');
 await expect(page.getByTestId('generation-status')).toContainText('failed');
 await expandEvidence(page);await expect(page.locator('article[id$="-card-sample-delver"]')).toContainText('Flying');
 await page.getByLabel('Your question').fill('Lightning Bolt');
 await page.getByRole('button',{name:'Send',exact:true}).click();
 await expandEvidence(page);await expect(page.getByRole('heading',{name:'Lightning Bolt',exact:true})).toBeVisible();
});

test('Stop aborts upstream even when cancel HTTP stalls and cannot overwrite a later turn', async ({page,request}) => {
 let release!: () => void;
 const held = new Promise<void>(resolve => {release=resolve;});
 let cancelRequested = false;
 await page.route('**/api/conversations/*/turns/*/cancel', async route => {
  cancelRequested = true;
  await held;
  await route.abort().catch(() => {});
 });
 try {
  await ask(page,'Delver stop');
  await expect(page.getByTestId('answer-text')).toHaveText('The transformed ');
  const boundedCancel = page.waitForEvent('requestfailed',{predicate:request => request.url().endsWith('/cancel')});
  await page.getByRole('button',{name:'Stop answer'}).click();
  await expect(page.getByLabel('Your question')).toBeEditable();
  await expect.poll(async () => {
   const conversations = await (await request.get('/api/conversations')).json();
   const detail = await (await request.get(`/api/conversations/${conversations[0].id}`)).json();
   return detail.turns[0].state;
  },{timeout:2000}).toBe('cancelled');
  expect(cancelRequested).toBe(true);
   await page.getByLabel('Your question').fill('Lightning Bolt');
  await page.getByRole('button',{name:'Send',exact:true}).click();
  await expandEvidence(page);await expect(page.getByRole('heading',{name:'Lightning Bolt',exact:true})).toBeVisible();
  await boundedCancel;
  await expect(page.getByRole('alert')).not.toBeVisible();
  const latest=page.locator('.turn').last();await latest.getByText('Retrieval details',{exact:true}).click();
  await expect(latest.getByTestId('actual-query')).toHaveText('Lightning Bolt');
 } finally {release();}
});
