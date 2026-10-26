import {expect, type Locator, type Page} from '@playwright/test';

export async function expandEvidence(scope: Page | Locator) {
 const page = 'page' in scope ? scope.page() : scope;
 await expect(page.getByLabel('Your question')).toHaveValue('');
 const disclosure = scope.locator('details.evidence').last();
 await expect(disclosure).toBeVisible();
 if (!await disclosure.evaluate(element => (element as HTMLDetailsElement).open)) {
  await disclosure.locator('summary').click();
 }
}
