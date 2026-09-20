import os
import sys
import re
import unicodedata
import warnings
import time
from difflib import SequenceMatcher

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

try:
    import paddlex.utils.deps as _paddlex_deps
    _paddlex_deps.require_extra = lambda *args, **kwargs: None
    _paddlex_deps.is_extra_available = lambda *args, **kwargs: True
    _paddlex_deps.is_dep_available = lambda *args, **kwargs: True
    _paddlex_deps.require_deps = lambda *args, **kwargs: None
except Exception:
    pass

import cv2
import numpy as np
from paddleocr import PaddleOCR

# Tận dụng tài nguyên CPU hợp lý
_cpu_count = os.cpu_count() or 4
cv2.setNumThreads(min(4, _cpu_count))

warnings.filterwarnings("ignore", message=r"No ccache found\..*", category=UserWarning)

try:
    from opencc import OpenCC
except ImportError:
    OpenCC = None


def format_timestamp(seconds: float) -> str:
    total_ms = max(0, round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


class VideoProcessor:
    """Xử lý video và trích xuất phụ đề thông minh với nhận diện thay đổi khung hình & đa luồng."""

    def __init__(self, subtitle_region_start=0.70, subtitle_region=None, orientation="auto"):
        self.subtitle_region_start = subtitle_region_start
        self.subtitle_region = subtitle_region
        self.orientation = orientation
        self.model = None
        self._traditional_to_simplified = OpenCC("t2s") if OpenCC else None

    def init_model(self, log_callback=None):
        if self.model is None:
            cpu_threads = min(8, max(2, _cpu_count - 1))
            if log_callback:
                log_callback(f"Đang tải PaddleOCR PP-OCRv5 mobile (sử dụng {cpu_threads} luồng CPU)...")
            self.model = PaddleOCR(
                text_detection_model_name="PP-OCRv5_mobile_det",
                text_recognition_model_name="PP-OCRv5_mobile_rec",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                enable_mkldnn=False,
                cpu_threads=cpu_threads,
            )

    def _normalise(self, text):
        text = unicodedata.normalize("NFKC", text)
        if self._traditional_to_simplified:
            text = self._traditional_to_simplified.convert(text)
        text = re.sub(r"[。．，,、；;：:！!？?\"'“”‘’·…—-]", "", text)
        return re.sub(r"\s+", "", text).strip()

    def _same_subtitle(self, first, second):
        first, second = self._normalise(first), self._normalise(second)
        if not first or not second:
            return False
        return first == second or SequenceMatcher(None, first, second).ratio() >= 0.75

    def _consensus_text(self, readings):
        readings = [item for item in readings if item]
        if not readings:
            return ""
        return max(readings, key=lambda candidate: sum(
            SequenceMatcher(None, self._normalise(candidate), self._normalise(other)).ratio()
            for other in readings
        ))

    @staticmethod
    def _is_valid_chinese_subtitle(text):
        """Lọc bỏ nhiễu OCR, logo và ký tự rác không phải phụ đề tiếng Trung."""
        compact = re.sub(r"\s+", "", text)
        if len(compact) < 1:
            return False
        chinese_count = len(re.findall(r"[\u3400-\u9fff]", compact))
        return chinese_count >= 1 and (chinese_count / len(compact)) >= 0.35

    def _orient_frame(self, frame, rotation=0):
        if rotation == 90:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif rotation == 180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        elif rotation == 270:
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        if self.orientation == "portrait" and frame.shape[1] > frame.shape[0]:
            return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        if self.orientation == "landscape" and frame.shape[0] > frame.shape[1]:
            return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return frame

    def _subtitle_crop(self, frame, rotation=0):
        frame = self._orient_frame(frame, rotation)
        height, width = frame.shape[:2]
        if self.subtitle_region:
            left, top, right, bottom = self.subtitle_region
            x1, x2 = sorted((int(left * width), int(right * width)))
            y1, y2 = sorted((int(top * height), int(bottom * height)))
            return frame[max(0, y1):min(height, y2), max(0, x1):min(width, x2)]
        return frame[int(height * self.subtitle_region_start):, :]

    @staticmethod
    def _has_text_potential(crop):
        """Kiểm tra nhanh xem vùng crop có khả năng chứa chữ hay là nền trống."""
        if crop is None or crop.size == 0:
            return False
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        # Độ tương phản giữa min và max
        if float(np.max(gray)) - float(np.min(gray)) < 25:
            return False
        # Độ lệch chuẩn (stddev) của ảnh
        if float(np.std(gray)) < 12.0:
            return False
        return True

    @staticmethod
    def _result_data(result):
        if isinstance(result, dict):
            return result.get("res", result)
        if hasattr(result, "json"):
            data = result.json
            data = data() if callable(data) else data
            if isinstance(data, dict):
                return data.get("res", data)
        return {}

    def _ocr_crop(self, crop):
        if crop is None or crop.size == 0:
            return ""
        
        # Tối ưu kích thước crop: chỉ phóng to nếu ảnh quá nhỏ để OCR
        h, w = crop.shape[:2]
        if h < 36:
            scale = 36.0 / h
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        elif h > 180:
            # Nếu crop quá lớn (ví dụ video 4K/2K), thu nhỏ lại để tăng tốc OCR gấp 4 lần mà vẫn cực nét
            scale = 180.0 / h
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

        lines = []
        try:
            for prediction in self.model.predict(crop):
                data = self._result_data(prediction)
                texts = data.get("rec_texts", [])
                scores = data.get("rec_scores", [])
                polygons = data.get("rec_polys", data.get("dt_polys", []))
                entries = []
                for index, value in enumerate(texts):
                    text = re.sub(r"\s+", " ", str(value)).strip()
                    score = float(scores[index]) if index < len(scores) else 1.0
                    if not text or score < 0.35:
                        continue
                    try:
                        y_position = min(point[1] for point in polygons[index])
                    except (IndexError, TypeError):
                        y_position = 0
                    entries.append((y_position, text))
                lines.extend(text for _, text in sorted(entries, key=lambda item: item[0]))
        except Exception:
            pass
        return "\n".join(lines)

    def extract_subtitles_from_video(self, video_path, log_callback=None, stop_event=None, pause_event=None):
        """Trích xuất phụ đề video tối ưu tốc độ và độ chính xác."""
        self.init_model(log_callback)
        video_path = os.path.normpath(video_path)
        capture = cv2.VideoCapture(video_path)
        if not capture.isOpened():
            raise RuntimeError(f"Không thể mở video: {video_path}")

        fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 1)
        total_duration = total_frames / fps
        rotation = int(capture.get(getattr(cv2, "CAP_PROP_ORIENTATION_META", 48)) or 0) % 360

        if log_callback:
            log_callback(f"Bắt đầu OCR: {os.path.basename(video_path)} | Thời lượng: {format_timestamp(total_duration)} ({total_frames} frames)...")

        # Quét ở tần suất ~2.5 - 3 FPS là tối ưu cho phụ đề video
        sample_step = max(1, round(fps / 2.5))
        
        active_text = ""
        active_start = None
        active_end = None
        active_readings = []
        missing_samples = 0
        subtitle_rows = []
        frame_index = 0
        
        prev_sig = None
        last_log_time = time.time()

        try:
            while True:
                if stop_event and stop_event.is_set():
                    break
                while pause_event and pause_event.is_set():
                    if stop_event and stop_event.is_set():
                        break
                    time.sleep(0.5)

                ok, frame = capture.read()
                if not ok:
                    break

                if frame_index % sample_step != 0:
                    frame_index += 1
                    continue

                timestamp = frame_index / fps
                crop = self._subtitle_crop(frame, rotation)

                # Tính signature nhỏ của khung hình để so sánh khác biệt với khung hình trước
                is_changed = True
                if crop is not None and crop.size > 0:
                    small = cv2.resize(crop, (64, 24), interpolation=cv2.INTER_AREA)
                    gray_small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                    if prev_sig is not None:
                        diff = float(np.mean(cv2.absdiff(gray_small, prev_sig)))
                        if diff < 2.8:
                            # Khung hình hầu như không thay đổi
                            is_changed = False
                    prev_sig = gray_small

                if not is_changed:
                    # Kế thừa kết quả của khung hình trước, không cần chạy lại mô hình OCR nặng
                    if active_text:
                        active_readings.append(active_text)
                        active_end = timestamp + (sample_step / fps)
                        missing_samples = 0
                else:
                    # Kiểm tra xem có dấu hiệu chữ không trước khi gọi AI OCR
                    if not self._has_text_potential(crop):
                        text = ""
                    else:
                        text = self._ocr_crop(crop)

                    if text and (not active_text or self._same_subtitle(active_text, text)):
                        if not active_text:
                            active_text, active_start, active_readings = text, timestamp, []
                        active_readings.append(text)
                        active_end = timestamp + (sample_step / fps)
                        missing_samples = 0
                    elif not text and active_text:
                        missing_samples += 1
                        if missing_samples >= 2:
                            subtitle_rows.append((active_start, active_end, self._consensus_text(active_readings)))
                            active_text = ""
                            active_start = active_end = None
                            active_readings = []
                            missing_samples = 0
                    else:
                        if active_text:
                            subtitle_rows.append((active_start, timestamp, self._consensus_text(active_readings)))
                        active_text, active_start = text, timestamp
                        active_end = timestamp + (sample_step / fps)
                        active_readings = [text] if text else []
                        missing_samples = 0

                frame_index += 1

                # Cập nhật log tiến độ thời gian thực
                now = time.time()
                if log_callback and (now - last_log_time >= 2.0 or frame_index >= total_frames - sample_step):
                    percent = min(100, int((frame_index / total_frames) * 100))
                    curr_str = format_timestamp(timestamp)
                    tot_str = format_timestamp(total_duration)
                    count_subs = len(subtitle_rows) + (1 if active_text else 0)
                    log_callback(f"[OCR {percent:3d}%] {curr_str} / {tot_str} | Đã tìm thấy {count_subs} câu phụ đề")
                    last_log_time = now

            if active_text and active_start is not None:
                subtitle_rows.append((active_start, active_end, self._consensus_text(active_readings)))

        finally:
            capture.release()

        # Lọc bỏ các dòng phụ đề rác hoặc quá ngắn
        subtitle_rows = [
            (start, end, text) for start, end, text in subtitle_rows
            if text and end - start >= 0.20 and self._is_valid_chinese_subtitle(text)
        ]

        if log_callback:
            log_callback(f"✓ Hoàn tất OCR video: Tổng cộng {len(subtitle_rows)} câu phụ đề hợp lệ.")

        return "".join(
            f"{index}\n{format_timestamp(start)} --> {format_timestamp(end)}\n{text}\n\n"
            for index, (start, end, text) in enumerate(subtitle_rows, start=1)
            if end > start
        )

    def transcribe_video(self, video_path, log_callback=None):
        return self.extract_subtitles_from_video(video_path, log_callback)
