import { test, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';

test.beforeAll(() => {
 execFileSync('uv', ['run', 'python', '-m', 'magic_rag', 'sample'], {cwd:'..', env:{...process.env,MAGIC_RAG_DB:process.env.MAGIC_RAG_TEST_DB || './test-results/browser.db'}});
});

test('reopen original evidence and delete saved conversations after page reload', async ({page}) => {
 const delverQuestion = `Delver ${Date.now()}`;
 const boltQuestion = `Lightning Bolt ${Date.now()}`;
 await page.goto('/');
 await page.getByLabel('Your question').fill(delverQuestion);
 await page.getByRole('button',{name:'Search cards'}).click();
 await expect(page.getByTestId('actual-query')).toHaveText(delverQuestion);
 await page.getByLabel('Your question').fill('Sol Ring');
 await page.getByRole('button',{name:'Search cards'}).click();
 await expect(page.getByTestId('actual-query')).toHaveText('Sol Ring');
 await page.getByRole('button',{name:'New conversation',exact:true}).click();
 await expect(page.getByTestId('actual-query')).toHaveCount(0);
 await page.getByLabel('Your question').fill(boltQuestion);
 await page.getByRole('button',{name:'Search cards'}).click();
 await expect(page.getByRole('heading',{name:'Lightning Bolt',exact:true})).toBeVisible();
 await page.reload();
 await page.getByRole('button',{name:`Open conversation: ${delverQuestion}`,exact:true}).click();
 await expect(page.getByTestId('actual-query')).toHaveText('Sol Ring');
 await page.getByRole('button',{name:`View turn 1: ${delverQuestion}`,exact:true}).click();
 await expect(page.getByTestId('actual-query')).toHaveText(delverQuestion);
 await expect(page.getByRole('heading',{name:'Delver of Secrets // Insectile Aberration'})).toBeVisible();
 await expect(page.getByText('Retrieval complete',{exact:true}).first()).toBeVisible();
 await page.getByRole('button',{name:`Delete conversation: ${delverQuestion}`,exact:true}).click();
 await expect(page.getByRole('button',{name:`Open conversation: ${delverQuestion}`,exact:true})).toHaveCount(0);
 await page.reload();
 await expect(page.getByRole('button',{name:`Open conversation: ${delverQuestion}`,exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:`Open conversation: ${boltQuestion}`,exact:true}).click();
 await expect(page.getByTestId('actual-query')).toHaveText(boltQuestion);
 await page.screenshot({path:'test-results/conversations-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
 await page.screenshot({path:'test-results/conversations-mobile.png',fullPage:true});
});
