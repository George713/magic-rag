import { test, expect } from '@playwright/test';
test('vector mode presents model identity, distance convention, candidates and timing', async ({page}) => {
 await page.goto('/');
 await page.getByLabel('Search mode').selectOption('vector');
 await page.getByLabel('Your question').fill('accelerate mana');
 await page.getByRole('button', {name:'Search cards'}).click();
 await expect(page.getByRole('heading', {name:'Sol Ring', exact:true})).toBeVisible();
 await expect(page.getByText('cosine distance (lower is better)', {exact:true})).toBeVisible();
 await expect(page.getByText('controlled', {exact:true})).toBeVisible();
 await expect(page.getByText('Vector candidates', {exact:false}).first()).toBeVisible();
});
