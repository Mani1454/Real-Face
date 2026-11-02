"""Run or benchmark the pinned local renderer with a realtime-oriented size."""
import argparse
import asyncio
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def configure_runtime():
    attention = os.environ.setdefault(
        'REAL_FACE_ATTENTION',
        'sage' if importlib.util.find_spec('sageattention') else 'sdpa',
    )
    # Older installs keep the previous compatible profile until setup is rerun.
    accelerated = attention == 'sage'
    os.environ.setdefault('REAL_FACE_RENDER_SIZE', '448' if accelerated else '384')
    os.environ.setdefault('REAL_FACE_FRAME_NUM', '25' if accelerated else '33')
    os.environ.setdefault('OPENSPLINE_COMPILE', '1')
    os.environ.setdefault('TORCHINDUCTOR_CACHE_DIR', str(ROOT / '.avatar-runtime/torch-compile'))
    from openspline_server import worker
    from renderer_runtime import configured_process_main
    worker._process_main = configured_process_main


def configure_video_transport():
    """Preserve portrait detail on localhost while retaining REMB adaptation."""
    from aiortc.codecs import h264, vpx
    bitrate = int(os.getenv('REAL_FACE_VIDEO_BITRATE', '1500000'))
    if not 250_000 <= bitrate <= 6_000_000:
        raise ValueError('REAL_FACE_VIDEO_BITRATE must be between 250000 and 6000000')
    for codec in (h264, vpx):
        codec.DEFAULT_BITRATE = bitrate
        codec.MAX_BITRATE = max(3_000_000, bitrate)


async def benchmark(settings, output, blocks=7, pace=False):
    import numpy as np
    from openspline_server.worker import Worker
    worker = Worker(settings.workers[0], settings)
    try:
        await worker.start()
        if not worker.ready:
            raise RuntimeError(worker.error)
        await worker.call('prepare', str(ROOT / 'code/static/tutor-portrait.png'), 0)
        history = np.zeros(worker.info['cache_samples'], dtype=np.float32)
        samples = worker.info['chunk_samples']
        tone = (0.1 * np.sin(2 * np.pi * 180 * np.arange(samples) / 16000)).astype(np.float32)
        timings = []
        for index in range(blocks):
            history = np.concatenate([history, tone])[-len(history):]
            frames, elapsed = await worker.call('infer', history)
            print(json.dumps({'block': index, 'seconds': round(elapsed, 4)}), flush=True)
            timings.append(elapsed)
            if pace and index > 0:
                await asyncio.sleep(max(0, samples / 16000 - elapsed))
        steady = timings[1:]
        report = {
            'render_size': int(os.getenv('REAL_FACE_RENDER_SIZE', '384')),
            'frame_num': int(os.getenv('REAL_FACE_FRAME_NUM', '33')),
            'attention': os.getenv('REAL_FACE_ATTENTION', 'sdpa'),
            'compiled': os.getenv('OPENSPLINE_COMPILE') == '1',
            'block_audio_seconds': samples / 16000,
            'warmup_seconds': timings[0],
            'steady_median_seconds': float(np.median(steady)),
            'steady_p95_seconds': float(np.percentile(steady, 95)),
            'steady_max_seconds': max(steady),
            'measured_blocks': len(steady),
            'paced_to_playback': pace,
            'generated_fps': len(frames) / float(np.mean(steady)),
            'frame_width': int(frames.shape[2]),
            'frame_height': int(frames.shape[1]),
            'realtime': max(steady) < samples / 16000,
            'scope': 'engine only; excludes transport and browser playback',
        }
        if output:
            Path(output).write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report), flush=True)
    finally:
        await worker.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark', action='store_true')
    parser.add_argument('--output')
    parser.add_argument('--blocks', type=int, default=7)
    parser.add_argument('--pace', action='store_true', help='Simulate realtime playback cadence')
    parser.add_argument('--port', type=int, default=7860)
    args = parser.parse_args()
    if args.blocks < 3:
        parser.error('--blocks must be at least 3')
    os.chdir(ROOT)
    configure_runtime()
    from openspline_server.config import Settings
    settings = Settings.from_file(str(ROOT / 'avatar-service.yaml'))
    settings.inference_timeout = 900  # Allow first-use compilation, then reuse its disk cache.
    if args.benchmark:
        asyncio.run(benchmark(settings, args.output, args.blocks, args.pace))
    else:
        configure_video_transport()
        import uvicorn
        import numpy as np
        from openspline_server.worker import WorkerPool

        original_start = WorkerPool.start

        async def warm_start(pool):
            await original_start(pool)
            for worker in pool.workers:
                if not worker.ready:
                    continue
                print('Warming renderer before accepting sessions; first compilation can take a few minutes.', flush=True)
                await worker.call('prepare', str(ROOT / 'code/static/tutor-portrait.png'), 0)
                history = np.zeros(worker.info['cache_samples'], dtype=np.float32)
                await worker.call('infer', history)
                await worker.call('reset')
                print('GPU renderer warm and ready.', flush=True)

        WorkerPool.start = warm_start
        from openspline_server.app import create_app
        uvicorn.run(create_app(settings), host='127.0.0.1', port=args.port, access_log=False)


if __name__ == '__main__':
    main()
