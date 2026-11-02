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
        frame_num = int(os.getenv('REAL_FACE_FRAME_NUM', '33'))
        if frame_num not in {17, 25, 33}:
            raise ValueError('REAL_FACE_FRAME_NUM must be 17, 25, or 33')
        attention = os.getenv('REAL_FACE_ATTENTION', 'sdpa')
        if attention not in {'sdpa', 'sage'}:
            raise ValueError('REAL_FACE_ATTENTION must be sdpa or sage')
        from openspline_server._vendor.flash_head import inference
        from openspline_server._vendor.flash_head.src.modules import flash_head_model
        if attention == 'sage' and not flash_head_model.SAGE_ATTN_AVAILABLE:
            raise RuntimeError('Install sageattention==1.0.6 in .avatar-venv to use Sage attention')
        flash_head_model.SAGE_ATTN_AVAILABLE = attention == 'sage'
        inference.infer_params['height'] = size
        inference.infer_params['width'] = size
        inference.infer_params['frame_num'] = frame_num
    original_rank_main(rank, world_size, settings, conn, port)


def configured_process_main(settings, conn):
    upstream_worker._rank_main = configured_rank_main
    original_process_main(settings, conn)
