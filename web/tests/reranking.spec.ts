import { test, expect } from '@playwright/test';
test('reranking inspector shows before and after positions and model identity', async ({page}) => {
 await page.goto('/');
 await page.getByLabel('Search mode').selectOption('hybrid_rerank');
 await page.getByLabel('Your question').fill('Sol Ring artifact');
 await page.getByText('Retrieval settings', {exact:true}).click();
 await page.getByLabel('Reranker shortlist').fill('2');
 await page.getByLabel('Evidence limit').fill('1');
 await page.getByRole('button', {name:'Send', exact:true}).click();
 await expect(page.getByRole('heading', {name:'Delver of Secrets // Insectile Aberration',exact:true})).toBeVisible();
 await page.locator('.turn').last().getByText('Retrieval details', {exact:true}).click();
 await expect(page.getByRole('heading', {name:'Fused candidates 3'})).toBeVisible();
 await expect(page.getByRole('heading', {name:'Reranked candidates 2'})).toBeVisible();
 await expect(page.getByText('Fused #2 → #1 · promoted 1', {exact:true})).toBeVisible();
 await expect(page.getByText('controlled-reranker', {exact:true})).toBeVisible();
 await page.screenshot({path:'test-results/reranking.png',fullPage:true});
});
