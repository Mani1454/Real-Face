"""Optional real-service check; use the test backend for credential-free transport QA.

This check proves session/audio/video plumbing, not photorealistic model quality.
Start a renderer separately and pass its URL. Requires the app on localhost:8000,
Node, @playwright/test, and Chrome (or Playwright's installed Chromium).
"""
import argparse
import asyncio
import json
import math
import struct
from pathlib import Path

from openspline import Openspline

ROOT = Path(__file__).resolve().parent.parent


async def check(url, app_url):
    async with Openspline(url=url, timeout=30).avatar(ROOT / 'code/static/tutor-portrait.png') as avatar:
        browser = await asyncio.create_subprocess_exec(
            'node', str(ROOT / 'scripts/renderer_browser_check.cjs'), app_url,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        )
        try:
            browser.stdin.write((json.dumps(avatar.session) + '\n').encode())
            await browser.stdin.drain()
            line = await asyncio.wait_for(browser.stdout.readline(), 30)
            if line.strip() != b'viewer_ready':
                raise RuntimeError('Browser did not connect to the renderer')
            await avatar.wait_for_viewer(timeout=15)
            pcm = b''.join(struct.pack('<h', int(4000 * math.sin(2 * math.pi * 220 * i / 24000))) for i in range(24000))
            await avatar.send_audio(pcm, sample_rate=24000)
            await avatar.end_turn()
            await avatar.interrupt()
            browser.stdin.write(b'finish\n')
            await browser.stdin.drain()
            stdout, _ = await asyncio.wait_for(browser.communicate(), 30)
            if browser.returncode:
                raise RuntimeError('Browser transport check failed')
            print(stdout.decode().strip())
            print('PASS: real SDK session, browser video, PCM playback/drain, interrupt, and cleanup. Model quality was not evaluated.')
        finally:
            if browser.returncode is None:
                browser.terminate()
                await browser.wait()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://localhost:7861')
    parser.add_argument('--app-url', default='http://localhost:8000')
    args = parser.parse_args()
    asyncio.run(check(args.url, args.app_url))
