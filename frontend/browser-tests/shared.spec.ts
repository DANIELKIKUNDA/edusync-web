import {test,expect} from '@playwright/test';
// The harness page (/browser-tests/harness.html) is served by the dev server only: on the compiled app it falls back to
// the sign-in screen (2026-10-31: it was counted as a failure in build runs).
test.skip(process.env.EDUSYNC_TEST_BUILD==='1','needs the dev server (harness page)');
for(const width of [320,390,480,768,1440]){
  test(`shared MFA, breadcrumb and page geometry at ${width}px`,async({page})=>{
    await page.setViewportSize({width,height:850});
    let requests=0;
    await page.route('**/api/v1/auth/platform/mfa/step-up',async route=>{requests++;await route.fulfill({json:{ok:true}})});
    await page.goto('/browser-tests/harness.html?scene=mfa');
    const input=page.getByRole('textbox');await expect(input).toBeFocused();
    for(const digit of '12345'){await page.keyboard.type(digit);await expect(input).toBeFocused();}
    await page.screenshot({path:`${process.env.EDUSYNC_TEST_OUTPUT||'test-results'}/mfa-${width}.png`});
    await page.keyboard.press('Backspace');await expect(input).toHaveValue('1234');
    await page.keyboard.type('56');await expect(page.getByRole('dialog')).toHaveCount(0);expect(requests).toBe(1);
    await expect.poll(()=>page.title()).toBe('Push — EduSync');
    await page.screenshot({path:`${process.env.EDUSYNC_TEST_OUTPUT||'test-results'}/trail-${width}.png`});
    const back=width<768?page.getByRole('button',{name:'Retour : Messagerie'}):page.getByRole('button',{name:'Messagerie',exact:true});
    await back.click();await expect.poll(()=>page.title()).toBe('Messagerie — EduSync');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:`${process.env.EDUSYNC_TEST_OUTPUT||'test-results'}/shared-${width}.png`});
  });
}
test('single scroll control, inactivity, safe-area collision, rotation and reduced motion',async({page})=>{
  await page.setViewportSize({width:390,height:850});await page.emulateMedia({reducedMotion:'reduce'});
  await page.goto('/browser-tests/harness.html');
  const down=page.getByRole('button',{name:'Aller en bas de la page'});await expect(down).toBeHidden();
  await page.evaluate(()=>scrollTo(0,1000));await expect(down).toBeVisible();
  await down.click();const up=page.getByRole('button',{name:'Revenir en haut de la page'});await expect(up).toBeVisible();
  await up.click();await expect(up).toBeHidden();
  await page.setViewportSize({width:850,height:390});await page.evaluate(()=>scrollTo(0,1000));await expect(down).toBeVisible();
  await page.evaluate(()=>{const b=document.createElement('button');b.id='business';b.textContent='Action métier';b.style.cssText='position:fixed;bottom:80px;left:calc(50% - 22px);width:44px;height:44px';document.body.append(b);dispatchEvent(new Event('resize'));});
  await expect(down).toBeHidden();await page.locator('#business').evaluate(e=>e.remove());
  await page.evaluate(()=>dispatchEvent(new Event('touchstart')));await expect(down).toBeVisible();
  await page.waitForTimeout(3800);await expect(down).toBeHidden();
  await page.keyboard.press('PageDown');await expect(page.locator('.pf-vertical')).toBeVisible();
});
