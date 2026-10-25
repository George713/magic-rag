import { test, expect } from '@playwright/test';
test('hybrid inspector distinguishes branch scores and fused ranks', async ({page}) => {
 await page.goto('/');
 await page.getByLabel('Search mode').selectOption('hybrid');
 await page.getByLabel('Your question').fill('Sol Ring');
 await page.getByRole('button', {name:'Search cards'}).click();
 await expect(page.getByRole('heading', {name:'Keyword candidates 1'})).toBeVisible();
 await expect(page.getByRole('heading', {name:'Vector candidates 3'})).toBeVisible();
 await expect(page.getByRole('heading', {name:'Fused candidates 3'})).toBeVisible();
 await expect(page.getByText('reciprocal rank fusion (higher is better)', {exact:true})).toBeVisible();
 await expect(page.getByText('keyword #1', {exact:false}).first()).toBeVisible();
 await page.getByText('Retrieval settings', {exact:true}).click();
 await page.getByLabel('Evidence limit').fill('1');
 await page.getByRole('button', {name:'Search cards'}).click();
 await expect(page.getByRole('heading', {name:'Sol Ring',exact:true})).toBeVisible();
 await expect(page.getByText('1 cards', {exact:true})).toBeVisible();
 await page.screenshot({path:'test-results/hybrid.png',fullPage:true});
});
