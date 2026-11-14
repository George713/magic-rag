import {expandEvidence} from './evidence';
import {test,expect} from '@playwright/test';

test.beforeEach(async ({request}) => {
 const response = await request.get('/api/conversations');
 for (const conversation of await response.json()) await request.delete(`/api/conversations/${conversation.id}`);
});

const lines = (scope: import('@playwright/test').Locator) => scope.getByRole('list',{name:'Searches'}).getByRole('listitem');

test('the live search line shows the model-written query on the first turn and on follow-ups, under unchanged filters',async ({page}) => {
 await page.goto('/');
 await page.getByLabel('Red',{exact:true}).check();
 await page.getByLabel('Creature',{exact:true}).check();
 await page.getByLabel('Maximum mana value',{exact:true}).fill('2');
 await page.getByLabel('Your question').fill('something red that eats artifacts');
 await page.getByRole('button',{name:'Send',exact:true}).click();
 const first=page.locator('section.turn').nth(0);
 // The model-written query is shown live, while the answer is still pending.
 await expect(lines(first)).toHaveText(['searching "Atog sacrifice an artifact creature" · 2 cards']);
 await expect(page.getByRole('button',{name:'Stop answer'})).toBeVisible();
 await expect(first.getByTestId('answer-text')).toHaveText('Atog sacrifices artifacts to grow.');
 await first.locator('.retrieval-details > summary').click();
 await expect(first.getByTestId('original-question')).toHaveText('something red that eats artifacts');
 await expect(first.getByTestId('actual-query')).toHaveText('Atog sacrifice an artifact creature');
 await expect(first.getByTestId('trace-filters')).toContainText('Red');
 await page.getByLabel('Your question').fill('Any cheaper ones?');
 await page.getByRole('button',{name:'Send',exact:true}).click();
 const second=page.locator('section.turn').nth(1);
 await expect(lines(second)).toHaveText(['searching "Atog artifact sacrifice cheaper creatures" · 2 cards']);
 await expect(page.getByLabel('Red',{exact:true})).toBeChecked();
 await expect(page.getByLabel('Maximum mana value',{exact:true})).toHaveValue('2');
 await expandEvidence(second);await expect(second.getByRole('heading',{name:'Atog',exact:true})).toBeVisible();
 await page.getByLabel('Your question').fill('simulate provider failure');
 await page.getByRole('button',{name:'Send',exact:true}).click();
 const third=page.locator('section.turn').nth(2);
 await expect(third.getByTestId('generation-status')).toContainText('Answer stream failed');
 await expect(lines(third)).toHaveCount(0);
 await page.reload();
 await page.getByRole('button',{name:'Open conversation: something red that eats artifacts',exact:true}).first().click();
 const reopened=page.locator('section.turn');
 // Reopened turns show their searches collapsed into a summary.
 await expect(reopened.locator('.search-summary > summary')).toHaveText([/^1 search /,/^1 search /]);
 await reopened.nth(1).locator('.search-summary > summary').click();
 await expect(lines(reopened.nth(1))).toHaveText(['searching "Atog artifact sacrifice cheaper creatures" · 2 cards']);
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
 await page.screenshot({path:'test-results/agent-mobile.png',fullPage:true});
});

test('a comparison shows one live line per search, collapses into "2 searches", and reopens collapsed',async ({page}) => {
 await page.goto('/');
 await page.getByLabel('Your question').fill('compare Atog and Goblin Engineer');
 await page.getByRole('button',{name:'Send',exact:true}).click();
 const turn=page.locator('section.turn').last();
 // Live, while the answer is pending: one line per search, in order.
 await expect(lines(turn)).toHaveText(['searching "Atog" · 1 card','searching "Goblin Engineer" · 1 card']);
 await expect(turn.getByTestId('answer-text')).toHaveCount(0);
 await expect(turn.getByTestId('answer-text')).toHaveText('Atog grows; Goblin Engineer returns artifacts.');
 // On completion the lines fold into one collapsed summary.
 const summary=turn.locator('.search-summary > summary');
 await expect(summary).toHaveText(/^2 searches/);
 await expect(lines(turn)).toHaveCount(0);
 await summary.click();
 await expect(lines(turn)).toHaveText(['searching "Atog" · 1 card','searching "Goblin Engineer" · 1 card']);
 const searches=turn.getByRole('region',{name:/^Search \d+$/});
 await expect(searches).toHaveCount(2);
 for (const [index,query] of [[1,'Atog'],[2,'Goblin Engineer']] as const) {
  const search=turn.getByRole('region',{name:`Search ${index}`,exact:true});
  await expect(search.getByTestId('actual-query')).toHaveText(query);
  await expect(search.getByRole('heading',{name:/Keyword candidates/})).toBeVisible();
  await expect(search.getByTestId('search-timings')).toContainText('keyword:');
 }
 await page.reload();
 await page.getByRole('button',{name:'Open conversation: compare Atog and Goblin Engineer',exact:true}).click();
 const reopened=page.locator('section.turn').last();
 await expect(reopened.locator('.search-summary > summary')).toHaveText(/^2 searches/);
 await expect(reopened.locator('.search-summary')).not.toHaveAttribute('open');
 await reopened.locator('.search-summary > summary').click();
 await expect(reopened.getByRole('region',{name:/^Search \d+$/})).toHaveCount(2);
 await expect(reopened.getByRole('region',{name:'Search 2',exact:true}).getByTestId('actual-query')).toHaveText('Goblin Engineer');
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
 await page.screenshot({path:'test-results/agent-multisearch-mobile.png',fullPage:true});
});
