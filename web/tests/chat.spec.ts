import {expandEvidence} from './evidence';
import {test,expect,type Page} from '@playwright/test';
import {installCardImages} from './card-images';
test.use({hasTouch:true});
test.beforeEach(async({page,request})=>{
 for(const chat of await(await request.get('/api/conversations')).json())await request.delete(`/api/conversations/${chat.id}`);
 await installCardImages(page);
});
async function send(page:Page,question:string){await page.getByLabel('Your question').fill(question);await page.getByRole('button',{name:'Send',exact:true}).click();}
test('selected cards and both faces share one scrollable row on desktop and mobile',async({page})=>{
 await page.setViewportSize({width:1100,height:900});
 await page.goto('/');await send(page,'Delver Lightning multiple assets only');
 const assets=page.getByRole('region',{name:'Card assets',exact:true});
 await expect(assets.getByRole('img')).toHaveCount(3);
 await expect(assets.getByRole('link')).toHaveCount(0);
 await expect(assets.locator('figcaption')).toHaveText(['Delver of Secrets','Insectile Aberration','Lightning Bolt']);
 for(const viewport of [{width:1100,height:900},{width:390,height:844}]){
  await page.setViewportSize(viewport);
  await assets.evaluate(element=>element.scrollLeft=0);
  await expect.poll(()=>assets.getByRole('img').evaluateAll(images=>images.every(image=>(image as HTMLImageElement).naturalWidth>0))).toBe(true);
  const boxes=await assets.getByRole('img').evaluateAll(images=>images.map(image=>{
   const box=image.getBoundingClientRect();return {x:box.x,y:box.y,width:box.width};
  }));
  expect(boxes.every(box=>Math.abs(box.y-boxes[0].y)<1&&box.width>=160)).toBe(true);
  expect(boxes[1].x-boxes[0].x-boxes[0].width).toBeGreaterThan(0);
  expect(boxes[2].x-boxes[1].x-boxes[1].width).toBeGreaterThan(0);
  expect(await assets.evaluate(element=>element.scrollWidth>element.clientWidth)).toBe(true);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  const first=assets.getByRole('button',{name:'Enlarge Delver of Secrets',exact:true});
  await first.focus();await page.keyboard.press('Tab');await page.keyboard.press('Tab');
  await expect(assets.getByRole('button',{name:'Enlarge Lightning Bolt',exact:true})).toBeFocused();
  await expect.poll(()=>assets.evaluate(element=>element.scrollLeft)).toBeGreaterThan(0);
  await expect(assets.getByRole('button',{name:'Enlarge Lightning Bolt',exact:true})).toBeInViewport({ratio:1});
  expect(await assets.locator('figure').evaluateAll(figures=>figures.every(figure=>{
   const image=figure.querySelector('img')!.getBoundingClientRect();
   const caption=figure.querySelector('figcaption')!;
   const box=caption.getBoundingClientRect();
   return getComputedStyle(caption).textAlign==='center'&&Math.abs((box.x+box.width/2)-(image.x+image.width/2))<1;
  }))).toBe(true);
  if(viewport.width===390){
   await assets.evaluate(element=>element.scrollLeft=0);
   const box=(await assets.boundingBox())!;
   const touch=await page.context().newCDPSession(page);
   const start=box.x+box.width-30,y=box.y+80;
   await touch.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:start,y}]});
   for(let step=1;step<=6;step++)await touch.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:start-step*35,y}]});
   await touch.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
   await expect.poll(()=>assets.evaluate(element=>element.scrollLeft)).toBeGreaterThan(0);
   await touch.detach();
  }
  await page.screenshot({path:`test-results/card-row-${viewport.width}.png`,fullPage:true});
 }
 await page.reload();await expect(assets.getByRole('img')).toHaveCount(3);
 await expect(assets.locator('figcaption')).toHaveText(['Delver of Secrets','Insectile Aberration','Lightning Bolt']);
});

test('automatic streaming, copy, followups and turn-specific evidence survive without Sources links',async({page})=>{
 await page.goto('/');await send(page,'Delver');
 await expect(page.getByTestId('answer-text')).toHaveText('The transformed face has flying.');
 await page.getByRole('button',{name:'Copy answer',exact:true}).click();
 await expect.poll(()=>page.evaluate(()=>navigator.clipboard.readText())).toBe('The transformed face has flying.');
 await send(page,'Show those again');await expect(page.getByTestId('answer-text')).toHaveCount(2);
 const last=page.locator('.turn').last();await last.getByText('Retrieval details',{exact:true}).click();
 await expect(last.getByTestId('actual-query')).toHaveText('Delver');
 await expect(page.getByRole('navigation',{name:'Answer citations'})).toHaveCount(0);
 await expect(page.locator('details.evidence').first()).not.toHaveAttribute('open','');
 await expect(page.locator('details.evidence').last()).not.toHaveAttribute('open','');
 await page.locator('details.evidence').first().locator('summary').click();
 await expect(page.locator('details.evidence').first()).toContainText('Flying');
 await expect(page.locator('details.evidence').last()).not.toHaveAttribute('open','');
 await page.reload();await expect(page.getByTestId('answer-text')).toHaveCount(2);
});
test('assets-only and combined responses display separate source images and both faces reopen',async({page})=>{
 await page.goto('/');await send(page,'Delver assets only');
 const assets=page.getByRole('region',{name:'Card assets',exact:true});await expect(assets).toBeVisible();
 await expect(page.getByTestId('answer-text')).toHaveCount(0);await expect(page.getByRole('button',{name:'Copy answer'})).toHaveCount(0);
 await expect(assets.getByRole('img')).toHaveCount(2);await expect(page.locator('details.evidence')).not.toHaveAttribute('open','');
 await assets.getByRole('button',{name:'Enlarge Insectile Aberration',exact:true}).click();
 await expect(page.getByRole('dialog')).toBeVisible();await page.getByRole('button',{name:'Close image'}).click();await expect(page.getByRole('dialog')).not.toBeVisible();
 await page.reload();await expect(assets.getByRole('img')).toHaveCount(2);await expect(page.locator('details.evidence')).not.toHaveAttribute('open','');
 await expect(assets.getByRole('link')).toHaveCount(0);await expandEvidence(page);await expect(page.locator('details.evidence')).toHaveAttribute('open','');
 await send(page,'Delver assets');const last=page.locator('.turn').last();await expect(last.getByTestId('answer-text')).toBeVisible();await expect(last.getByRole('region',{name:'Card assets'})).toBeVisible();
});
test('failed images keep selected asset names and evidence readable',async({page})=>{
 await page.unroute('https://cards.test/**');await page.route('https://cards.test/**',route=>route.abort());
 await page.goto('/');await send(page,'Delver assets only');
 await expect(page.getByRole('region',{name:'Card assets'}).getByText('Image unavailable: Delver of Secrets')).toBeVisible();
 await expandEvidence(page);await expect(page.locator('.card-text')).toContainText('Flying');
 await page.getByText('Retrieval details',{exact:true}).click();await expect(page.getByTestId('actual-query')).toHaveText('Delver assets only');
});
test('Stop and provider failure retain incomplete output and permit subsequent turns',async({page})=>{
 await page.goto('/');await send(page,'Delver stop');await expect(page.getByTestId('answer-text')).toHaveText('The transformed ');
 await page.getByRole('button',{name:'Stop answer'}).click();await expect(page.getByTestId('generation-status')).toContainText('stopped');
 await send(page,'Delver fail');await expect(page.locator('.turn').last().getByTestId('generation-status')).toContainText('failed');
 await expandEvidence(page);await expect(page.locator('.turn').last().locator('.card-text')).toContainText('Flying');
 await page.reload();await expect(page.getByTestId('answer-text')).toHaveCount(2);
});
test('ordinary source image and legacy asset without imagery remain usable',async({page})=>{
 await page.goto('/');await send(page,'Lightning Bolt assets only');
 await expect(page.getByRole('region',{name:'Card assets'}).getByRole('img')).toHaveCount(1);
 expect(await page.getByRole('region',{name:'Card assets'}).evaluate(element=>element.scrollWidth===element.clientWidth)).toBe(true);
 await page.getByRole('region',{name:'Card assets'}).getByRole('button',{name:'Enlarge Lightning Bolt',exact:true}).click();
 await page.getByRole('button',{name:'Close image',exact:true}).click();
 await send(page,'Sol Ring assets only');
 const assets=page.locator('.turn').last().getByRole('region',{name:'Card assets'});
 await expect(assets.getByText('Sol Ring',{exact:true})).toBeVisible();
 await expect(assets.getByRole('img')).toHaveCount(0);await expect(assets.getByRole('link')).toHaveCount(0);
 await page.reload();await expect(page.locator('.turn').last().getByRole('region',{name:'Card assets'}).getByText('Sol Ring',{exact:true})).toBeVisible();
});
