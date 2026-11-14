import {expect, type Locator, type Page} from '@playwright/test';

export async function expandEvidence(scope: Page | Locator) {
 const page = 'page' in scope ? scope.page() : scope;
 await expect(page.getByLabel('Your question')).toHaveValue('');
 // The question clears when the turn starts, before its search returns; wait for the latest turn's evidence.
 const turn = 'page' in scope ? scope : scope.locator('.turn').last();
 const disclosure = turn.locator('details.evidence').last();
 await expect(disclosure).toBeVisible();
 if (!await disclosure.evaluate(element => (element as HTMLDetailsElement).open)) {
  await disclosure.locator('summary').click();
 }
}
