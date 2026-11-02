const {test, expect} = require('@playwright/test');

// Contract fake; exercises browser lifecycle without claiming GPU inference.
const fakePlayer = `
export class AvatarConnection extends EventTarget {
  constructor(session, video) { super(); this.video = video; }
  async connect() { this.dispatchEvent(new CustomEvent('statechange', {detail:'ready'})); }
  async play() {}
  close() { this.dispatchEvent(new CustomEvent('statechange', {detail:'disconnected'})); }
}`;

async function mockFace(page, messages) {
  await page.route('**/static/vendor/openspline/index.js', route => route.fulfill({
    contentType: 'application/javascript', body: fakePlayer,
  }));
  await page.routeWebSocket('**/ws', socket => {
    socket.onMessage(raw => {
      const data = JSON.parse(raw);
      messages.push(data);
      if (data.type === 'avatar_start') socket.send(JSON.stringify({type:'avatar_session',content:{id:'test',url:'http://renderer.invalid',token:'viewer'}}));
    });
  });
}

test('credential-free preview loads assets, disables voice, and fits desktop/mobile', async ({page}) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.setViewportSize({width:1440,height:1080});
  await page.goto('/');
  await expect(page.getByRole('heading', {name:/Good conversations/})).toBeVisible();
  await expect(page.locator('#setupNotice')).toContainText('Preview mode');
  await expect(page.locator('#startBtn')).toBeDisabled();
  await expect(page.locator('#chatInput')).toBeDisabled();
  await expect(page.locator('#avatarVideo')).toBeHidden();
  expect(await page.locator('.tutor-portrait').evaluate(image => image.complete && image.naturalWidth > 0)).toBe(true);
  expect((await page.request.get('/static/vendor/openspline/index.js')).ok()).toBe(true);
  await page.screenshot({path:'test-results/real-face-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.locator('#menuBtn').click();
  await expect(page.locator('#sidebar')).toBeVisible();
  await page.locator('#closeSidebarBtn').click();
  await expect(page.locator('#sidebar')).toBeHidden();
  await page.screenshot({path:'test-results/real-face-mobile.png',fullPage:true});
  expect(errors).toEqual([]);
});

test('renderer failure is visible and connection can be retried', async ({page}) => {
  let starts = 0;
  await page.routeWebSocket('**/ws', socket => socket.onMessage(raw => {
    if (JSON.parse(raw).type === 'avatar_start') {
      starts++;
      socket.send(JSON.stringify({type:'avatar_error',content:'Live face unavailable. Start the renderer.'}));
    }
  }));
  await page.goto('/');
  await page.locator('#avatarConnectBtn').click();
  await expect(page.locator('#avatarStatus')).toContainText('Start the renderer');
  await expect(page.locator('#avatarConnectBtn')).toHaveText('Connect live face');
  await page.locator('#avatarConnectBtn').click();
  await expect.poll(() => starts).toBe(2);
});

test('viewer readiness, interruption, and disconnect follow the session contract', async ({page}) => {
  const messages = [];
  await mockFace(page, messages);
  await page.goto('/');
  await page.locator('#avatarConnectBtn').click();
  await expect(page.locator('#avatarConnectBtn')).toHaveText('Disconnect face');
  await expect(page.locator('#avatarVideo')).toBeVisible();
  await expect.poll(() => messages.some(x => x.type === 'avatar_ready')).toBe(true);
  await page.locator('#interruptBtn').click();
  await expect.poll(() => messages.some(x => x.type === 'avatar_interrupt')).toBe(true);
  await expect.poll(() => messages.some(x => x.type === 'interrupt')).toBe(true);
  expect(messages.filter(x => x.type === 'clear_history')).toHaveLength(1);
  await page.locator('#avatarConnectBtn').click();
  await expect(page.locator('#avatarVideo')).toBeHidden();
  await expect.poll(() => messages.some(x => x.type === 'avatar_stop')).toBe(true);
});

test('reachable voice server shows READY without reserving a conversation', async ({page}) => {
  let connections = 0;
  await page.route('**/api/config', route => route.fulfill({
    contentType:'application/json', body:JSON.stringify({voice_ready:true,missing_credentials:[],avatar_enabled:true}),
  }));
  await page.routeWebSocket('**/ws', () => { connections++; });
  await page.goto('/');
  await expect(page.locator('#statusText')).toHaveText('READY');
  await expect(page.locator('#startBtn')).toBeEnabled();
  expect(connections).toBe(0);
});

test('status recovers automatically after a temporary server outage', async ({page}) => {
  await page.clock.install();
  let unavailable = true;
  await page.route('**/api/config', route => unavailable ? route.abort() : route.fulfill({
    contentType:'application/json', body:JSON.stringify({voice_ready:true,missing_credentials:[],avatar_enabled:true}),
  }));
  await page.goto('/');
  await expect(page.locator('#statusText')).toHaveText('OFFLINE');
  await expect(page.locator('#setupNotice')).toContainText('Retrying automatically');
  unavailable = false;
  await page.clock.fastForward(10001);
  await expect(page.locator('#statusText')).toHaveText('READY');
  await expect(page.locator('#setupNotice')).toBeHidden();
});
