"""Performance adapter for the pinned OpenSpline 0.1.2 GPU worker.

Keep inference code upstream; customize its supported spatial inference parameters
inside each spawned GPU process before the pipeline is constructed.
"""
import os
from openspline_server import worker as upstream_worker

original_rank_main = upstream_worker._rank_main
original_process_main = upstream_worker._process_main


def configured_rank_main(rank, world_size, settings, conn, port):
    if settings['backend'] == 'gpu':
        size = int(os.getenv('REAL_FACE_RENDER_SIZE', '384'))
        if size not in {320, 384, 448, 512}:
            raise ValueError('REAL_FACE_RENDER_SIZE must be 320, 384, 448, or 512')
        from openspline_server._vendor.flash_head import inference
        inference.infer_params['height'] = size
        inference.infer_params['width'] = size
    original_rank_main(rank, world_size, settings, conn, port)


def configured_process_main(settings, conn):
    upstream_worker._rank_main = configured_rank_main
    original_process_main(settings, conn)
