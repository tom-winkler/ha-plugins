from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Optional

from log import log


def convert_audio_to_wav(audio_file_name: str) -> Optional[str]:
    def convert_with_ffmpeg(input_file_name: str, output_file_name: str) -> bool:
        try:
            subprocess.run(
                [
                    'ffmpeg',
                    '-y',
                    '-hide_banner',
                    '-loglevel',
                    'error',
                    '-i',
                    input_file_name,
                    output_file_name,
                ],
                check=True,
            )
            return True
        except Exception as e:
            log(None, f'Error converting audio with ffmpeg: {e}')
            return False

    def convert_with_pydub(input_file_name: str, output_file_name: str) -> bool:
        try:
            import pydub  # Lazy import: pydub depends on audioop, missing in Python 3.13

            _, file_extension = os.path.splitext(input_file_name)
            if file_extension == '.mp3':
                audio_segment = pydub.AudioSegment.from_mp3(input_file_name)
            elif file_extension == '.ogg':
                audio_segment = pydub.AudioSegment.from_ogg(input_file_name)
            elif file_extension == '.wav':
                audio_segment = pydub.AudioSegment.from_wav(input_file_name)
            else:
                return False

            audio_segment.export(output_file_name, format='wav')
            return True
        except Exception as e:
            log(None, f'Error converting audio with pydub: {e}')
            return False

    _, file_extension = os.path.splitext(audio_file_name)
    if not os.path.exists(audio_file_name):
        print('Error: could not find audio file:', audio_file_name)
        return None
    if file_extension not in ['.mp3', '.ogg', '.wav']:
        log(None, f'Error: could not figure out file format (.mp3, .ogg, .wav is supported): {audio_file_name}')
        return None
    try:
        wave_file_handler = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        wave_file_name = wave_file_handler.name
        wave_file_handler.close()

        if convert_with_pydub(audio_file_name, wave_file_name):
            return wave_file_name
        if convert_with_ffmpeg(audio_file_name, wave_file_name):
            return wave_file_name

        return None
    except Exception as e:
        log(None, f'Error converting audio file to wav: {e}')
        return None


def convert_mp3_stream_to_wav_file(stream: bytes) -> Optional[str]:
    mp3_file_handler = tempfile.NamedTemporaryFile(suffix='.mp3')
    mp3_file_handler.write(stream)
    return convert_audio_to_wav(mp3_file_handler.name)


def write_wav_stream_to_wav_file(stream: bytes) -> Optional[str]:
    wav_file_handler = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    wav_file_handler.write(stream)
    return wav_file_handler.name
