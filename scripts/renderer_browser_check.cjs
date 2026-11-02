const {chromium} = require('@playwright/test');
const readline = require('node:readline');
const fs = require('node:fs');
(async () => {
  const lines = readline.createInterface({input:process.stdin});
  const iterator = lines[Symbol.asyncIterator]();
  const session = JSON.parse((await iterator.next()).value);
  const browser = await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL || undefined,args:['--autoplay-policy=no-user-gesture-required']});
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(process.argv[2]);
    await page.evaluate(async descriptor => {
      window.realFace.attach(descriptor);
    }, session);
    await page.waitForFunction(() => window.realFace.active, {timeout:20000});
    await page.waitForFunction(() => document.querySelector('#avatarVideo').readyState >= 2, {timeout:20000});
    process.stdout.write('viewer_ready\n');
    await iterator.next();
    const video = await page.locator('#avatarVideo').evaluate(video => ({width:video.videoWidth,height:video.videoHeight,currentTime:video.currentTime}));
    if (!video.width || !video.height || !video.currentTime) throw new Error('No decoded video frames');
    if (errors.length) throw new Error(errors.join('\n'));
    fs.mkdirSync('test-results', {recursive:true});
    await page.screenshot({path:'test-results/real-renderer-transport.png',fullPage:true});
    await page.evaluate(() => window.realFace.disconnect(false));
    process.stdout.write(JSON.stringify(video)+'\n');
  } finally {
    await browser.close();
    lines.close();
  }
})().catch(error => {console.error(error.message);process.exit(1);});
