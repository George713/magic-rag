import {expandEvidence} from './evidence';
import {test,expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
test.beforeAll(()=>{execFileSync('uv',['run','python','-m','magic_rag','sample'],{cwd:'..',env:{...process.env,MAGIC_RAG_DB:'./test-results/browser.db'}});});
test.beforeEach(async({request})=>{for(const chat of await(await request.get('/api/conversations')).json())await request.delete(`/api/conversations/${chat.id}`);});
test('search shows complete card evidence and the turn query in expandable details',async({page})=>{
 await page.goto('/');await page.getByLabel('Your question').fill('Delver');await page.getByRole('button',{name:'Send',exact:true}).click();
 await expandEvidence(page);await expect(page.getByRole('heading',{name:'Delver of Secrets // Insectile Aberration'})).toBeVisible();await expandEvidence(page);await expect(page.locator('.card-text')).toContainText('Flying');
 await page.getByText('Retrieval details',{exact:true}).click();await expect(page.getByTestId('actual-query')).toHaveText('Delver');
 await page.getByLabel('Your question').fill('noresultxyz');await page.getByRole('button',{name:'Send',exact:true}).click();await expect(page.getByText('No matching cards',{exact:true})).toBeVisible();
});
test('mobile conversation and side panels remain within viewport',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/');await page.getByLabel('Your question').fill('Lightning Bolt');await page.getByRole('button',{name:'Send',exact:true}).click();
 await expandEvidence(page);await expect(page.getByRole('heading',{name:'Lightning Bolt',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Chats',exact:true}).click();await expect(page.getByRole('button',{name:'New chat',exact:true})).toBeVisible();await page.getByRole('button',{name:'Close history',exact:true}).click();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
