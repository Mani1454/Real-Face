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
  let channel;
  await page.route('**/static/vendor/openspline/index.js', route => route.fulfill({
    contentType: 'application/javascript', body: fakePlayer,
  }));
  await page.routeWebSocket('**/ws', socket => {
    channel = socket;
    socket.onMessage(raw => {
      const data = JSON.parse(raw);
      messages.push(data);
      if (data.type === 'avatar_start') socket.send(JSON.stringify({type:'avatar_session',content:{id:'test',url:'http://renderer.invalid',token:'viewer'}}));
    });
  });
  return data => channel.send(JSON.stringify(data));
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
  expect(messages.filter(x => x.type === 'avatar_interrupt')).toHaveLength(0);
  expect(await page.locator('#avatarVideo').evaluate(video => video.muted)).toBe(true);
  await expect.poll(() => messages.some(x => x.type === 'interrupt')).toBe(true);
  expect(messages.filter(x => x.type === 'clear_history')).toHaveLength(0);
  await page.locator('#avatarConnectBtn').click();
  await expect(page.locator('#avatarVideo')).toBeHidden();
  await expect.poll(() => messages.some(x => x.type === 'avatar_stop')).toBe(true);
  await page.locator('#resetBtn').click();
  await expect.poll(() => messages.filter(x => x.type === 'clear_history').length).toBe(1);
});

test('a stalled face connection times out, ignores late sessions, and can be retried', async ({page}) => {
  await page.clock.install();
  await page.route('**/api/config', route => route.fulfill({
    contentType:'application/json', body:JSON.stringify({voice_ready:false,missing_credentials:[],avatar_enabled:true,avatar_connect_timeout_ms:45000}),
  }));
  let channel, starts = 0;
  const descriptor = {id:'test',url:'http://renderer.invalid',token:'viewer'};
  await page.route('**/static/vendor/openspline/index.js', route => route.fulfill({
    contentType:'application/javascript',body:fakePlayer,
  }));
  await page.routeWebSocket('**/ws', socket => {
    channel = socket;
    socket.onMessage(raw => {
      if (JSON.parse(raw).type === 'avatar_start' && ++starts === 2) {
        socket.send(JSON.stringify({type:'avatar_session',content:descriptor}));
      }
    });
  });
  await page.goto('/');
  await page.locator('#avatarConnectBtn').click();
  await expect.poll(() => starts).toBe(1);
  await page.clock.fastForward(45001);
  await expect(page.locator('#avatarConnectBtn')).toHaveText('Connect live face');
  await expect(page.locator('#avatarStatus')).toContainText('took too long');
  channel.send(JSON.stringify({type:'avatar_session',content:descriptor}));
  await expect(page.locator('#avatarVideo')).toBeHidden();
  await page.locator('#avatarConnectBtn').click();
  await expect(page.locator('#avatarConnectBtn')).toHaveText('Disconnect face');
  await page.clock.fastForward(45001);
  await expect(page.locator('#avatarConnectBtn')).toHaveText('Disconnect face');
});

test('Cloud initialization can take longer than the local connection window', async ({page}) => {
  await page.clock.install();
  await page.route('**/api/config', route => route.fulfill({
    contentType:'application/json', body:JSON.stringify({voice_ready:false,missing_credentials:[],avatar_enabled:true,avatar_connect_timeout_ms:195000}),
  }));
  await page.route('**/static/vendor/openspline/index.js', route => route.fulfill({
    contentType:'application/javascript', body:fakePlayer,
  }));
  let channel;
  const messages = [];
  await page.routeWebSocket('**/ws', socket => {
    channel = socket;
    socket.onMessage(raw => messages.push(JSON.parse(raw)));
  });
  await page.goto('/');
  await expect.poll(() => page.evaluate(() => window.realFace.connectTimeoutMs)).toBe(195000);
  await page.locator('#avatarConnectBtn').click();
  await expect.poll(() => messages.some(x => x.type === 'avatar_start')).toBe(true);
  await page.clock.fastForward(60000);
  await expect(page.locator('#avatarConnectBtn')).toHaveText('Cancel connection');
  expect(messages.some(x => x.type === 'avatar_failed')).toBe(false);
  channel.send(JSON.stringify({type:'avatar_session',content:{id:'test',url:'http://renderer.invalid',token:'viewer'}}));
  await expect(page.locator('#avatarConnectBtn')).toHaveText('Disconnect face');
  await page.clock.fastForward(200000);
  await expect(page.locator('#avatarConnectBtn')).toHaveText('Disconnect face');
});

test('cancel and retry while the voice socket opens sends only one face start', async ({page}) => {
  await page.goto('/');
  await page.evaluate(() => {
    window.faceStarts = [];
    const ready = new Promise(resolve => { window.releaseVoiceConnection = resolve; });
    window.realFace.configure({connect:() => ready,send:data => window.faceStarts.push(data.type)});
  });
  await page.locator('#avatarConnectBtn').click();
  await page.locator('#avatarConnectBtn').click();
  await page.locator('#avatarConnectBtn').click();
  await page.evaluate(() => window.releaseVoiceConnection());
  await expect.poll(() => page.evaluate(() => window.faceStarts.filter(x => x === 'avatar_start').length)).toBe(1);
});

test('reachable voice server shows READY without reserving a conversation', async ({page}) => {
  let connections = 0;
  await page.route('**/api/config', route => route.fulfill({
    contentType:'application/json', body:JSON.stringify({voice_ready:true,missing_credentials:[],avatar_enabled:true}),
  }));
  await page.routeWebSocket('**/ws', () => { connections++; });
  await page.goto('/', {waitUntil:'networkidle', timeout:5000});
  await expect(page.locator('#statusText')).toHaveText('READY');
  await expect(page.locator('#startBtn')).toBeEnabled();
  await page.locator('#interruptBtn').click();
  await expect(page.locator('#liveText')).toHaveText('Go ahead, I’m listening.');
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

test('generation completion does not unlock input before audio playback drains', async ({page}) => {
  const messages=[];
  const send=await mockFace(page,messages);
  await page.goto('/');
  await page.locator('#avatarConnectBtn').click();
  await expect(page.locator('#avatarConnectBtn')).toHaveText('Disconnect face');
  send({type:'avatar_turn_start'});
  await page.evaluate(()=>{
    const connection=window.realFace.connection;
    connection.dispatchEvent(new CustomEvent('statechange',{detail:'speaking'}));
    connection.dispatchEvent(new CustomEvent('statechange',{detail:'speaking'}));
    connection.dispatchEvent(new Event('turnend'));
  });
  await expect(page.locator('#orbContainer')).toHaveClass(/speaking/);
  await expect.poll(()=>messages.filter(x=>x.type==='tts_start').length).toBe(1);
  send({type:'avatar_turn_end'});
  await expect(page.locator('#orbContainer')).not.toHaveClass(/speaking/);
  await expect.poll(()=>messages.filter(x=>x.type==='tts_stop').length).toBe(1);
});

test('Your turn mutes immediately and ignores stale speaking events until a new turn', async ({page}) => {
  const messages=[];
  const send=await mockFace(page,messages);
  await page.goto('/');
  await page.locator('#avatarConnectBtn').click();
  await expect(page.locator('#avatarConnectBtn')).toHaveText('Disconnect face');
  send({type:'avatar_turn_start'});
  await page.evaluate(()=>window.realFace.connection.dispatchEvent(new CustomEvent('statechange',{detail:'speaking'})));
  await page.locator('#interruptBtn').click();
  await page.evaluate(()=>window.realFace.connection.dispatchEvent(new CustomEvent('statechange',{detail:'speaking'})));
  expect(await page.locator('#avatarVideo').evaluate(video=>video.muted)).toBe(true);
  await expect(page.locator('#orbContainer')).not.toHaveClass(/speaking/);
  await expect.poll(()=>messages.filter(x=>x.type==='interrupt').length).toBe(1);
  expect(messages.filter(x=>x.type==='avatar_interrupt')).toHaveLength(0);
  send({type:'avatar_turn_start'});
  await page.waitForFunction(()=>!window.realFace.interrupted);
  await page.evaluate(()=>window.realFace.connection.dispatchEvent(new CustomEvent('statechange',{detail:'speaking'})));
  expect(await page.locator('#avatarVideo').evaluate(video=>video.muted)).toBe(false);
});
