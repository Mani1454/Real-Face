"""Compare local WebRTC compression using an existing generated tutor recording.

Run with .avatar-venv/bin/python scripts/check_video_codec.py recording.webm.
PSNR measures additional codec distortion, not neural-avatar realism.
"""
import argparse
import json
import time
from fractions import Fraction

import av
import numpy as np
from aiortc.codecs.vpx import Vp8Decoder, Vp8Encoder, VpxPayloadDescriptor
from aiortc.jitterbuffer import JitterFrame


def measure(images, bitrate):
    encoder, decoder = Vp8Encoder(), Vp8Decoder()
    encoder.target_bitrate = bitrate
    timings, errors, size = [], [], 0
    for index, reference in enumerate(images):
        frame = av.VideoFrame.from_ndarray(reference, format='rgb24')
        frame.pts, frame.time_base = index * 3600, Fraction(1, 90000)
        start = time.perf_counter()
        payloads, timestamp = encoder.encode(frame, index == 0)
        timings.append(time.perf_counter() - start)
        data = b''.join(VpxPayloadDescriptor.parse(p)[1] for p in payloads)
        size += len(data)
        for decoded in decoder.decode(JitterFrame(data=data, timestamp=timestamp)):
            output = decoded.to_ndarray(format='rgb24').astype(np.float32)
            errors.append(float(np.mean((output - reference.astype(np.float32)) ** 2)))
    if len(errors) != len(images):
        raise RuntimeError('Not every input frame decoded successfully')
    return {
        'target_bitrate': bitrate, 'frames': len(images),
        'psnr_db': round(float(10 * np.log10(255 ** 2 / np.mean(errors))), 2),
        'mean_encode_ms': round(float(np.mean(timings) * 1000), 2),
        'encoded_bytes': size,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording')
    args = parser.parse_args()
    images = []
    with av.open(args.recording) as container:
        for frame in container.decode(video=0):
            images.append(frame.to_ndarray(format='rgb24'))
            if len(images) == 75:
                break
    if not images:
        parser.error('The recording has no video frames')
    for bitrate in (500_000, 1_500_000):
        print(json.dumps(measure(images, bitrate)), flush=True)


if __name__ == '__main__':
    main()
