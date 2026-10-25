import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';

test.beforeEach(async ({request}) => {
 const response = await request.get('/api/conversations');
 for (const conversation of await response.json()) await request.delete(`/api/conversations/${conversation.id}`);
});

async function ask(page: Page, question: string) {
 await page.goto('/');
 await page.getByLabel('Include a cited explanation').check();
 await page.getByLabel('Your question').fill(question);
 await page.getByRole('button',{name:'Search cards'}).click();
}

test('answer text arrives incrementally and completed answers reopen', async ({page}) => {
 await ask(page,'Delver');
 await expect(page.getByTestId('answer-text')).toHaveText('The transformed ');
 await expect(page.getByRole('button',{name:'Stop answer'})).toBeVisible();
 await expect(page.getByTestId('answer-text')).toHaveText('The transformed face has flying.');
 await expect(page.getByRole('button',{name:'Stop answer'})).not.toBeVisible();
 await expect(page.getByTestId('answer-citations').getByRole('link')).toHaveAttribute('href','#card-sample-delver');
 await page.reload();
 await page.getByRole('button',{name:'Open conversation: Delver',exact:true}).click();
 await expect(page.getByTestId('answer-text')).toHaveText('The transformed face has flying.');
 await expect(page.getByRole('button',{name:'View turn 1: Delver'})).toContainText('Completed');
});

test('Stop preserves incomplete output and reopening shows cancelled state', async ({page}) => {
 await ask(page,'Delver stop');
 await expect(page.getByTestId('answer-text')).toHaveText('The transformed ');
 await page.getByRole('button',{name:'Stop answer'}).click();
 await expect(page.getByRole('button',{name:'Search cards'})).toBeEnabled();
 await expect(page.getByTestId('generation-status')).toContainText('stopped');
 await expect(page.getByTestId('answer-text')).toHaveText('The transformed ');
 await page.reload();
 await page.getByRole('button',{name:'Open conversation: Delver stop',exact:true}).click();
 await expect(page.getByRole('button',{name:'View turn 1: Delver stop'})).toContainText('Cancelled');
 await expect(page.getByTestId('answer-text')).toHaveText('The transformed ');
 await expect(page.getByTestId('answer-citations')).not.toBeVisible();
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
 await page.screenshot({path:'test-results/stopped-mobile.png',fullPage:true});
});

test('provider failure keeps partial output, source cards, and subsequent turns usable', async ({page}) => {
 await ask(page,'Delver fail');
 await expect(page.getByTestId('answer-text')).toHaveText('The transformed ');
 await expect(page.getByTestId('generation-status')).toContainText('failed');
 await expect(page.locator('article#card-sample-delver')).toContainText('Flying');
 await page.getByLabel('Include a cited explanation').uncheck();
 await page.getByLabel('Your question').fill('Lightning Bolt');
 await page.getByRole('button',{name:'Search cards'}).click();
 await expect(page.getByRole('heading',{name:'Lightning Bolt',exact:true})).toBeVisible();
});
