import { test, expect } from '@playwright/test';
test('vector mode presents model identity, distance convention, candidates and timing', async ({page}) => {
 await page.goto('/');
 await page.getByLabel('Search mode').selectOption('vector');
 await page.getByLabel('Your question').fill('accelerate mana');
 await page.getByRole('button', {name:'Send', exact:true}).click();
 await expect(page.getByRole('heading', {name:'Sol Ring', exact:true})).toBeVisible();
 await page.locator('.turn').last().getByText('Retrieval details', {exact:true}).click();
 await expect(page.getByText('cosine distance (lower is better)', {exact:true})).toBeVisible();
 await expect(page.getByText('embedding model', {exact:true}).locator('..').locator('pre')).toContainText('"model": "controlled"');
 await expect(page.getByRole('heading', {name:'Vector candidates', exact:false})).toBeVisible();
});
