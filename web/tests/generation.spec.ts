import { test, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';

test.beforeAll(() => {
 execFileSync('uv', ['run', 'python', '-m', 'magic_rag', 'sample'], {cwd:'..', env:{...process.env, MAGIC_RAG_DB:'./test-results/browser.db'}});
});

test('requested explanation preserves sources when the provider is unconfigured', async ({ page }) => {
 await page.goto('/');
 await page.getByLabel('Include a cited explanation').check();
 await page.getByLabel('Your question').fill('Delver');
 await page.getByRole('button', {name: 'Search cards'}).click();
 await expect(page.getByRole('heading', {name: 'Card explanation'})).toBeVisible();
 await expect(page.getByTestId('generation-status')).toContainText('not configured');
 await expect(page.locator('article#card-sample-delver')).toContainText('Flying');
});

test('answer citations navigate to the exact selected card evidence', async ({ page }) => {
 await page.route('**/api/conversations/*/turns/*/stream', async route => {
  const generation = {status:'completed', message:'Answer grounded in selected card evidence.', text:'The transformed face has flying.', insufficient_evidence:false, citations:[{card_id:'sample-delver',name:'Delver of Secrets // Insectile Aberration'}]};
  await route.fulfill({status:200,contentType:'application/x-ndjson',body:JSON.stringify({event:'done',generation})+'\n'});
 });
 await page.goto('/');
 await page.getByLabel('Include a cited explanation').check();
 await page.getByLabel('Your question').fill('Delver');
 await page.getByRole('button', {name: 'Search cards'}).click();
 await expect(page.getByTestId('answer-text')).toHaveText('The transformed face has flying.');
 const citation = page.getByTestId('answer-citations').getByRole('link');
 await citation.click();
 await expect(page).toHaveURL(/#card-sample-delver$/);
 await expect(page.locator('article#card-sample-delver')).toContainText('look at the top card');
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
 await page.screenshot({path:'test-results/answer-mobile.png',fullPage:true});
});
