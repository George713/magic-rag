import {test, expect, type Page} from '@playwright/test';
import {installCardImages} from './card-images';
import {expandEvidence} from './evidence';

test.beforeEach(async ({page, request}) => {
 for (const chat of await (await request.get('/api/conversations')).json()) {
  await request.delete(`/api/conversations/${chat.id}`);
 }
 await installCardImages(page);
});

async function showCardAssets(page: Page) {
 await page.goto('/');
 await page.getByLabel('Your question').fill('Delver assets only');
 await page.getByRole('button', {name: 'Send', exact: true}).click();
 await expect(page.getByRole('region', {name: 'Card assets'})).toBeVisible();
}

test('clicking an enlarged card closes it and returns focus to its thumbnail', async ({page}) => {
 await showCardAssets(page);
 const thumbnail = page.getByRole('region', {name: 'Card assets'}).getByRole('button', {name: 'Enlarge Insectile Aberration', exact: true});
 await thumbnail.click();
 const viewer = page.getByRole('dialog', {name: 'Insectile Aberration enlarged image'});
 await expect(viewer).toBeVisible();
 await viewer.getByRole('img', {name: 'Insectile Aberration', exact: true}).click();
 await expect(viewer).not.toBeVisible();
 await expect(thumbnail).toBeFocused();
});

for (const location of ['answer', 'evidence'] as const) {
 test(`all dismissal methods restore focus for ${location} images and saved faces reopen`, async ({page}) => {
  await showCardAssets(page);
  const scope = location === 'answer'
   ? page.getByRole('region', {name: 'Card assets'})
   : page.locator('details.evidence');
  if (location === 'evidence') await expandEvidence(page);
  const front = scope.getByRole('button', {name: 'Enlarge Delver of Secrets', exact: true});
  const back = scope.getByRole('button', {name: 'Enlarge Insectile Aberration', exact: true});
  for (const method of ['X', 'caption', 'backdrop', 'Escape', 'keyboard close']) {
   const thumbnail = method === 'caption' ? back : front;
   await thumbnail.focus();
   await thumbnail.press('Enter');
   const viewer = page.getByRole('dialog');
   await expect(viewer).toBeVisible();
   const close = viewer.getByRole('button', {name: 'Close image', exact: true});
   if (method === 'X') await close.click();
   if (method === 'caption') await viewer.getByText('Insectile Aberration', {exact: true}).click();
   if (method === 'backdrop') await page.mouse.click(4, 4);
   if (method === 'Escape') await page.keyboard.press('Escape');
   if (method === 'keyboard close') {
    await close.focus();
    await page.keyboard.press('Space');
   }
   await expect(viewer).not.toBeVisible();
   await expect(thumbnail).toBeFocused();
  }
  await page.reload();
  if (location === 'evidence') await expandEvidence(page);
  await back.click();
  const viewer = page.getByRole('dialog', {name: 'Insectile Aberration enlarged image'});
  await expect(viewer.getByRole('img')).toHaveAttribute('src', 'https://cards.test/delver-back.jpg');
  await expect(viewer.getByText('Insectile Aberration', {exact: true})).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(back).toBeFocused();
 });
}

for (const viewport of [{width: 1440, height: 1000}, {width: 390, height: 844}]) {
 test(`frameless viewer fits ${viewport.width}px viewport with floating caption and overlaid X`, async ({page}, testInfo) => {
  await page.setViewportSize(viewport);
  await showCardAssets(page);
  await page.getByRole('region', {name: 'Card assets'}).getByRole('button', {name: 'Enlarge Insectile Aberration', exact: true}).click();
  const viewer = page.getByRole('dialog');
  const image = viewer.getByRole('img', {name: 'Insectile Aberration', exact: true});
  const caption = viewer.getByText('Insectile Aberration', {exact: true});
  const close = viewer.getByRole('button', {name: 'Close image', exact: true});
  await expect(image).toBeVisible();
  await expect(caption).toBeInViewport();
  await expect(close).toBeInViewport();
  const surface = await viewer.evaluate(element => ({
   background: getComputedStyle(element).backgroundColor,
   border: getComputedStyle(element).borderTopWidth,
   backdrop: getComputedStyle(element, '::backdrop').backgroundColor
  }));
  expect(surface.background).toBe('rgba(0, 0, 0, 0)');
  expect(surface.border).toBe('0px');
  expect(surface.backdrop).toBe('rgba(3, 8, 6, 0.87)');
  const imageBox = (await image.boundingBox())!;
  const captionBox = (await caption.boundingBox())!;
  const closeBox = (await close.boundingBox())!;
  expect(imageBox.x).toBeGreaterThanOrEqual(0);
  expect(imageBox.y).toBeGreaterThanOrEqual(0);
  expect(imageBox.x + imageBox.width).toBeLessThanOrEqual(viewport.width);
  expect(imageBox.y + imageBox.height).toBeLessThan(captionBox.y);
  expect(Math.abs(imageBox.x + imageBox.width / 2 - viewport.width / 2)).toBeLessThan(2);
  expect(Math.abs(imageBox.x + imageBox.width / 2 - captionBox.x - captionBox.width / 2)).toBeLessThan(2);
  expect(closeBox.x).toBeGreaterThan(imageBox.x + imageBox.width / 2);
  expect(closeBox.x + closeBox.width).toBeLessThanOrEqual(imageBox.x + imageBox.width);
  expect(closeBox.y).toBeGreaterThanOrEqual(imageBox.y);
  expect(closeBox.y + closeBox.height).toBeLessThan(imageBox.y + imageBox.height / 2);
  await page.screenshot({path: testInfo.outputPath(`viewer-${viewport.width}.png`)});
 });
}
