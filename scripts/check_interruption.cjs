/* Optional live-provider check: measure the real Your turn control. */
const {chromium}=require('@playwright/test');
(async()=>{
  const browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome',args:['--autoplay-policy=no-user-gesture-required']});
  try {
    const page=await browser.newPage();
    const sent=[];
    page.on('websocket',socket=>{
      if(!socket.url().endsWith('/ws'))return;
      socket.on('framesent',event=>{
        if(typeof event.payload==='string')try{sent.push(JSON.parse(event.payload).type);}catch{}
      });
    });
    await page.goto(process.argv[2]||'http://localhost:8000');
    await page.waitForFunction(()=>window.realFace.active,null,{timeout:180000});
    await page.locator('#chatInput').fill('Tell me a short sentence about visiting a park.');
    await page.locator('#sendBtn').click();
    await page.waitForFunction(()=>window.realFace.speaking,null,{timeout:60000});
    await page.evaluate(()=>{
      const state=window.interruptionCheck={};
      const video=document.querySelector('#avatarVideo');
      document.querySelector('#interruptBtn').addEventListener('click',()=>{state.clickedAt=performance.now();},{capture:true,once:true});
      const pause=video.pause.bind(video);
      video.pause=()=>{pause();state.pausedAt=performance.now();state.muted=video.muted;state.paused=video.paused;};
      const handle=window.realFace.handleMessage.bind(window.realFace);
      window.realFace.handleMessage=message=>{
        if(message.type==='avatar_interrupted')state.acknowledgedAt=performance.now();
        return handle(message);
      };
    });
    await page.locator('#interruptBtn').click();
    await page.waitForFunction(()=>window.interruptionCheck.acknowledgedAt>0,null,{timeout:10000});
    const result=await page.evaluate(()=>{
      const state=window.interruptionCheck;
      return {pauseMs:state.pausedAt-state.clickedAt,serverClearMs:state.acknowledgedAt-state.clickedAt,mutedImmediately:state.muted,pausedImmediately:state.paused};
    });
    result.interruptRequests=sent.filter(type=>type==='interrupt').length;
    result.duplicateAvatarInterrupts=sent.filter(type=>type==='avatar_interrupt').length;
    result.passed=result.pauseMs<100&&result.serverClearMs<2000&&result.mutedImmediately&&result.pausedImmediately&&result.interruptRequests===1&&result.duplicateAvatarInterrupts===0;
    await page.close();
    console.log(JSON.stringify(result));
    if(!result.passed)process.exitCode=1;
  }finally{await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
