"""Low-priority background worker for hard-subtitle OCR."""
import os
import sys

class _DummyWriter:
    def write(self, *args, **kwargs):
        pass
    def flush(self, *args, **kwargs):
        pass
    def isatty(self):
        return False

if sys.stdout is None:
    sys.stdout = _DummyWriter()
if sys.stderr is None:
    sys.stderr = _DummyWriter()

import psutil


from video_processor import VideoProcessor


def run_ocr(video_path, subtitle_region, orientation, result_path):
    err_file = result_path + ".err"
    try:
        try:
            psutil.Process(os.getpid()).nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        except (psutil.Error, AttributeError):
            pass
        processor = VideoProcessor(subtitle_region=subtitle_region, orientation=orientation)
        srt = processor.extract_subtitles_from_video(video_path)
        with open(result_path, "w", encoding="utf-8-sig") as output:
            output.write(srt)
    except Exception as e:
        import traceback
        try:
            with open(err_file, "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except Exception:
            pass
        raise


if __name__ == "__main__":
    run_ocr(*sys.argv[1:])

