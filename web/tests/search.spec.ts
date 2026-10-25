import { test, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';

test.beforeAll(() => {
  execFileSync('uv', ['run', 'python', '-m', 'magic_rag', 'sample'], { cwd: '..', env: { ...process.env, MAGIC_RAG_DB: './test-results/browser.db' } });
});

test('search shows complete card evidence and actual query in inspector', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Your question').fill('Delver');
  await page.getByRole('button', { name: 'Search cards' }).click();
  await expect(page.getByRole('heading', { name: 'Delver of Secrets // Insectile Aberration' })).toBeVisible();
  await expect(page.getByText('Flying', { exact: false }).first()).toBeVisible();
  await expect(page.getByTestId('actual-query')).toHaveText('Delver');
  await expect(page.getByText('controlled-sample-v1', {exact: true})).toBeVisible();
  await page.getByLabel('Your question').fill('noresultxyz');
  await page.getByRole('button', { name: 'Search cards' }).click();
  await expect(page.getByText('No matching cards')).toBeVisible();
});

test('mobile search remains within the viewport', async ({ page }) => {
 await page.setViewportSize({width: 390, height: 844});
 await page.goto('/');
 await page.getByLabel('Your question').fill('Lightning Bolt');
 await page.getByRole('button', {name: 'Search cards'}).click();
 await expect(page.getByRole('heading', {name:'Lightning Bolt', exact:true})).toBeVisible();
 expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
 await page.screenshot({path:'test-results/mobile.png',fullPage:true});
});
