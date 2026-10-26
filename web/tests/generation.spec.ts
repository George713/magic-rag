import {expandEvidence} from './evidence';
import {test,expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
test.beforeAll(()=>{execFileSync('uv',['run','python','-m','magic_rag','sample'],{cwd:'..',env:{...process.env,MAGIC_RAG_DB:'./test-results/browser.db'}});});
test.beforeEach(async({request})=>{for(const chat of await(await request.get('/api/conversations')).json())await request.delete(`/api/conversations/${chat.id}`);});
test('automatic answer preserves evidence when the provider is unconfigured',async({page})=>{
 await page.goto('/');await page.getByLabel('Your question').fill('Delver');await page.getByRole('button',{name:'Send',exact:true}).click();
 await expect(page.getByTestId('generation-status')).toContainText('not configured');
 await expandEvidence(page);await expect(page.locator('.card-text')).toContainText('Flying');
 await expect(page.getByLabel('Include a cited explanation')).toHaveCount(0);
});
