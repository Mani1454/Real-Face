/* Optional real-provider + GPU browser smoke check. No mock renderer is used. */
const {chromium} = require('@playwright/test');
const fs = require('node:fs');
(async () => {
  const browser = await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL || 'chrome',headless:true,args:['--autoplay-policy=no-user-gesture-required']});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1080}});
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(process.argv[2] || 'http://localhost:8000');
    await page.waitForFunction(()=>!document.querySelector('#chatInput').disabled,null,{timeout:15000});
    await page.locator('#avatarConnectBtn').click();
    await page.waitForFunction(()=>window.realFace.active || document.querySelector('#setupNotice').textContent.includes('Another conversation'),null,{timeout:240000});
    if(!await page.evaluate(()=>window.realFace.active)) throw new Error('Another conversation is active. Close it before running this check.');
    await page.waitForFunction(()=>document.querySelector('#avatarVideo').readyState>=2,null,{timeout:120000});
    await page.evaluate(()=>{
      const state=window.liveFaceCheck={started:false,ended:false,frames:0,maxPixelDifference:0,inferenceMs:[],generatedSamples:0};
      const video=document.querySelector('#avatarVideo');
      const canvas=document.createElement('canvas'); canvas.width=64; canvas.height=64;
      const context=canvas.getContext('2d',{willReadFrequently:true});
      let previous;
      state.timer=setInterval(()=>{
        if(!state.started || state.ended || video.readyState<2) return;
        context.drawImage(video,0,0,64,64);
        const current=context.getImageData(0,0,64,64).data;
        if(previous) {
          let difference=0;
          for(let i=0;i<current.length;i+=4) difference+=Math.abs(current[i]-previous[i])+Math.abs(current[i+1]-previous[i+1])+Math.abs(current[i+2]-previous[i+2]);
          state.maxPixelDifference=Math.max(state.maxPixelDifference,difference/(64*64*3));
        }
        previous=new Uint8ClampedArray(current); state.frames++;
      },150);
      const start=window.realFace.options.onSpeaking;
      const end=window.realFace.options.onTurnEnd;
      window.realFace.options.onSpeaking=()=>{state.started=true;state.startedAt=performance.now();start();};
      window.realFace.options.onTurnEnd=()=>{if(state.started){state.ended=true;state.endedAt=performance.now();}end();};
      window.realFace.connection.addEventListener('event',event=>{
        if(event.detail?.type==='speaking') {
          state.inferenceMs.push(event.detail.inference_ms);
          state.generatedSamples=event.detail.generated_samples;
        }
      });
      state.recorded=[];
      state.recorder=new MediaRecorder(video.srcObject,{mimeType:'video/webm;codecs=vp8,opus'});
      state.recorder.ondataavailable=event=>{if(event.data.size)state.recorded.push(event.data);};
      state.recorder.start(250);
    });
    await page.locator('#chatInput').fill('Hello, I went to the park today.');
    await page.evaluate(()=>{window.liveFaceCheck.submittedAt=performance.now();});
    await page.locator('#sendBtn').click();
    await page.waitForFunction(()=>window.liveFaceCheck.started,null,{timeout:180000});
    fs.mkdirSync('test-results',{recursive:true});
    await page.locator('#avatarVideo').screenshot({path:'test-results/live-face-speaking.png'});
    await page.waitForFunction(()=>window.liveFaceCheck.ended,null,{timeout:180000});
    const result=await page.evaluate(async()=>{
      const state=window.liveFaceCheck;
      clearInterval(state.timer);
      await new Promise(resolve=>{state.recorder.onstop=resolve;state.recorder.stop();});
      const bytes=new Uint8Array(await new Blob(state.recorded,{type:'video/webm'}).arrayBuffer());
      let binary=''; for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
      const video=document.querySelector('#avatarVideo');
      const reports=await window.realFace.connection.pc?.getStats();
      const inbound=reports && [...reports.values()].find(item=>item.type==='inbound-rtp' && item.kind==='video');
      const codec=inbound && reports.get(inbound.codecId);
      const videoStats=inbound ? {
        codec:codec?.mimeType,framesPerSecond:inbound.framesPerSecond,
        framesDecoded:inbound.framesDecoded,framesDropped:inbound.framesDropped,
        packetsLost:inbound.packetsLost,jitterMs:Math.round((inbound.jitter || 0)*1000),
        meanJitterBufferMs:inbound.jitterBufferEmittedCount
          ? Math.round(inbound.jitterBufferDelay/inbound.jitterBufferEmittedCount*1000):null,
      }:null;
      return {frames:state.frames,maxPixelDifference:state.maxPixelDifference,width:video.videoWidth,height:video.videoHeight,
        firstSpeakingMs:Math.round(state.startedAt-state.submittedAt),
        playbackMs:Math.round(state.endedAt-state.startedAt),
        generatedAudioMs:Math.round(state.generatedSamples/48),inferenceMs:state.inferenceMs,videoStats,recording:btoa(binary)};
    });
    fs.writeFileSync('test-results/live-face-demo.webm',Buffer.from(result.recording,'base64'));
    delete result.recording;
    result.reply=await page.locator('.log-entry.assistant .log-text').last().textContent();
    result.pageErrors=errors;
    result.passed=result.frames>1 && result.maxPixelDifference>0.1 && !!result.reply && errors.length===0;
    await page.screenshot({path:'test-results/live-face-app.png',fullPage:true});
    await page.locator('#avatarConnectBtn').click();
    console.log(JSON.stringify(result));
    if(!result.passed)process.exitCode=1;
  } finally {await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
