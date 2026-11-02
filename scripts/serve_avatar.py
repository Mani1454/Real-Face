"""Run or benchmark the pinned local renderer with a realtime-oriented size."""
import argparse
import asyncio
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def configure_runtime():
    os.environ.setdefault('OPENSPLINE_COMPILE', '1')
    os.environ.setdefault('TORCHINDUCTOR_CACHE_DIR', str(ROOT / '.avatar-runtime/torch-compile'))
    from openspline_server import worker
    from renderer_runtime import configured_process_main
    worker._process_main = configured_process_main


async def benchmark(settings, output):
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
        for index in range(7):
            history = np.concatenate([history, tone])[-len(history):]
            frames, elapsed = await worker.call('infer', history)
            print(json.dumps({'block': index, 'seconds': round(elapsed, 4)}), flush=True)
            timings.append(elapsed)
        steady = timings[1:]
        report = {
            'render_size': int(os.getenv('REAL_FACE_RENDER_SIZE', '384')),
            'compiled': os.getenv('OPENSPLINE_COMPILE') == '1',
            'block_audio_seconds': samples / 16000,
            'warmup_seconds': timings[0],
            'steady_median_seconds': float(np.median(steady)),
            'steady_p95_seconds': float(np.percentile(steady, 95)),
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
    parser.add_argument('--port', type=int, default=7860)
    args = parser.parse_args()
    os.chdir(ROOT)
    configure_runtime()
    from openspline_server.config import Settings
    settings = Settings.from_file(str(ROOT / 'avatar-service.yaml'))
    settings.inference_timeout = 900  # Allow first-use compilation, then reuse its disk cache.
    if args.benchmark:
        asyncio.run(benchmark(settings, args.output))
    else:
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
