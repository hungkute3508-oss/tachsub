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

import shutil
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox

import re
import json
import subprocess
import multiprocessing
import tempfile
import cv2
from PIL import Image, ImageTk

from video_processor import VideoProcessor
from ocr_worker import run_ocr
from chatgpt_automation import ChatGPTAutomator

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Auto Video Translator - Trích xuất kịch bản")
        self.geometry("950x750")
        
        self.input_dir = ctk.StringVar()
        self.output_dir = ctk.StringVar()
        self.is_running = False
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.ocr_process = None
        self.subtitle_region = None
        self.video_orientation = ctk.StringVar(value="Tu dong")
        self.roi_status = ctk.StringVar(value="Vung sub: chua chon (mac dinh 30% phia duoi)")
        
        self.create_widgets()
        
    def create_widgets(self):
        # 1. Khung chọn thư mục
        frame_dir = ctk.CTkFrame(self)
        frame_dir.pack(pady=10, padx=20, fill="x")
        ctk.CTkButton(frame_dir, text="Xem truoc va khoanh sub", command=self.preview_subtitle_region, width=170).grid(row=0, column=3, padx=(0, 10), pady=10)
        ctk.CTkOptionMenu(frame_dir, variable=self.video_orientation, values=["Tu dong", "Doc", "Ngang"], width=115).grid(row=1, column=3, padx=(0, 10), pady=10)
        ctk.CTkLabel(frame_dir, textvariable=self.roi_status, text_color="#67c587").grid(row=3, column=0, columnspan=4, pady=(0, 8), sticky="w", padx=10)
        
        ctk.CTkLabel(frame_dir, text="Thư mục chứa video gốc:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        ctk.CTkEntry(frame_dir, textvariable=self.input_dir, width=400).grid(row=0, column=1, padx=10, pady=10)
        ctk.CTkButton(frame_dir, text="Chọn", command=self.select_input, width=80).grid(row=0, column=2, padx=10, pady=10)
        
        ctk.CTkLabel(frame_dir, text="Thư mục lưu kết quả:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        ctk.CTkEntry(frame_dir, textvariable=self.output_dir, width=400).grid(row=1, column=1, padx=10, pady=10)
        ctk.CTkButton(frame_dir, text="Chọn", command=self.select_output, width=80).grid(row=1, column=2, padx=10, pady=10)

        # Hướng dẫn mở Cốc Cốc
        help_text = 'LƯU Ý: Phải mở Cốc Cốc bằng lệnh:\n"C:\\Program Files\\CocCoc\\Browser\\Application\\browser.exe" --remote-debugging-port=9223\nvà mở sẵn tab ChatGPT!'
        ctk.CTkLabel(frame_dir, text=help_text, text_color="orange").grid(row=2, column=0, columnspan=3, pady=5)

        # 2. Khung Prompt
        frame_prompt = ctk.CTkFrame(self)
        frame_prompt.pack(pady=10, padx=20, fill="both", expand=True)
        
        ctk.CTkLabel(frame_prompt, text="Prompt ChatGPT:").pack(anchor="w", padx=10, pady=(10, 0))
        self.prompt_text = ctk.CTkTextbox(frame_prompt, height=100)
        self.prompt_text.pack(padx=10, pady=10, fill="x")
        default_prompt = (
            "Bạn là một chuyên gia biên tập nội dung và ngôn ngữ. Thay vì dịch thuật sát nghĩa, nhiệm vụ của bạn là VIẾT LẠI đoạn phụ đề SRT từ tiếng Trung sang tiếng Việt sao cho hoàn toàn phù hợp với văn phong, cách nói chuyện tự nhiên của người Việt Nam, mượt mà, dễ hiểu, trong khi VẪN GIỮ ĐƯỢC ĐẦY ĐỦ NỘI DUNG và ý nghĩa của video gốc.\n"
            "QUY TẮC BẮT BUỘC (Nếu vi phạm, hệ thống sẽ bị lỗi):\n"
            "1. TUYỆT ĐỐI KHÔNG trò chuyện, KHÔNG giải thích, KHÔNG đưa ra đề xuất hay bình luận.\n"
            "2. CHỈ TRẢ VỀ nội dung file SRT đã được viết lại, giữ nguyên định dạng số thứ tự và thời gian (timestamp).\n"
            "3. Nếu phụ đề gốc bị lỗi nhận diện hoặc câu từ lủng củng, hãy tự động suy luận ngữ cảnh để viết lại thành câu hoàn chỉnh và tự nhiên nhất, KHÔNG ĐƯỢC phàn nàn.\n"
            "4. Bắt buộc xử lý toàn bộ nội dung từ đầu đến cuối trong một câu trả lời duy nhất, không được tự ý cắt xén hay chia nhỏ đoạn.\n"
            "5. TUYỆT ĐỐI KHÔNG GIỮ LẠI BẤT KỲ KÝ TỰ TIẾNG TRUNG NÀO trong kết quả. Kết quả trả về 100% phải là tiếng Việt.\n"
            "6. CỰC KỲ QUAN TRỌNG: Câu văn tiếng Việt sau khi viết lại phải ngắn gọn, súc tích, đảm bảo KHÔNG ĐƯỢC dài hơn thời lượng đọc của câu gốc (phải khớp hoàn toàn với video). Ưu tiên diễn đạt thoát ý, linh hoạt, miễn là người xem hiểu trọn vẹn nội dung.\n"
            "Dưới đây là phụ đề cần xử lý:"
        )
        self.prompt_text.insert("0.0", default_prompt)
        
        # 3. Khung Log
        ctk.CTkLabel(frame_prompt, text="Tiến trình (Log):").pack(anchor="w", padx=10, pady=(5, 0))
        self.log_text = ctk.CTkTextbox(frame_prompt, state="disabled")
        self.log_text.pack(padx=10, pady=10, fill="both", expand=True)

        # 4. Khung Control
        frame_control = ctk.CTkFrame(self)
        frame_control.pack(pady=10, padx=20, fill="x")
        
        self.progress = ctk.CTkProgressBar(frame_control)
        self.progress.pack(pady=10, padx=20, fill="x")
        self.progress.set(0)
        
        self.btn_start = ctk.CTkButton(frame_control, text="BẮT ĐẦU", command=self.start_process, fg_color="green", hover_color="darkgreen")
        self.btn_start.pack(side="left", padx=10, pady=10, expand=True, fill="x")
        
        self.btn_pause = ctk.CTkButton(frame_control, text="TẠM DỪNG", command=self.toggle_pause, fg_color="#d37e00", hover_color="#b06900", state="disabled")
        self.btn_pause.pack(side="left", padx=10, pady=10, expand=True, fill="x")
        
        self.btn_stop = ctk.CTkButton(frame_control, text="DỪNG", command=self.stop_process, fg_color="red", hover_color="darkred", state="disabled")
        self.btn_stop.pack(side="right", padx=10, pady=10, expand=True, fill="x")

    def select_input(self):
        d = filedialog.askdirectory()
        if d: self.input_dir.set(d)
        
    def select_output(self):
        d = filedialog.askdirectory()
        if d: self.output_dir.set(d)

    def preview_subtitle_region(self):
        initial_dir = self.input_dir.get() if os.path.isdir(self.input_dir.get()) else os.getcwd()
        video_path = filedialog.askopenfilename(title="Chon video de khoanh vung phu de", initialdir=initial_dir, filetypes=[("Video", "*.mp4 *.mkv *.avi *.mov")])
        if not video_path:
            return
        capture = cv2.VideoCapture(video_path)
        if not capture.isOpened():
            messagebox.showerror("Loi", "Khong the mo video da chon.")
            return
        fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
        duration = max(0.1, (capture.get(cv2.CAP_PROP_FRAME_COUNT) or 1) / fps)
        rotation = self._get_video_rotation(video_path, capture)
        capture.release()
        window = ctk.CTkToplevel(self)
        window.title("Khoanh vung phu de")
        window.geometry("860x720")
        window.transient(self)
        ctk.CTkLabel(window, text="Chon khung co phu de, keo chuot de khoanh vung can OCR.").pack(pady=(12, 4))
        video_info = ctk.CTkLabel(window, text="Dang doc thong tin video...", text_color="#a8b3bf")
        video_info.pack(pady=(0, 4))
        canvas_width, canvas_height = 800, 500
        canvas = ctk.CTkCanvas(window, width=canvas_width, height=canvas_height, bg="black", highlightthickness=0)
        canvas.pack(padx=20, pady=8)
        time_label = ctk.CTkLabel(window, text="0.0s")
        time_label.pack()
        slider = ctk.CTkSlider(window, from_=0, to=duration)
        slider.pack(fill="x", padx=30, pady=(4, 12))
        preview_capture = cv2.VideoCapture(video_path)
        state = {"start": None, "rectangle": None, "selection": None, "image_box": None, "action": None, "original": None, "preview_after": None}

        def show_frame(value=0):
            preview_capture.set(cv2.CAP_PROP_POS_MSEC, float(value) * 1000)
            ok, frame = preview_capture.read()
            if not ok:
                return
            if rotation == 90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif rotation == 180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            elif rotation == 270:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
            if self.video_orientation.get() == "Doc" and frame.shape[1] > frame.shape[0]:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif self.video_orientation.get() == "Ngang" and frame.shape[0] > frame.shape[1]:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            source_width, source_height = image.size
            scale = min(canvas_width / source_width, canvas_height / source_height)
            display_width = max(1, round(source_width * scale))
            display_height = max(1, round(source_height * scale))
            image = image.resize((display_width, display_height), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            canvas.delete("all")
            offset_x = (canvas_width - display_width) // 2
            offset_y = (canvas_height - display_height) // 2
            canvas.create_image(offset_x, offset_y, anchor="nw", image=photo)
            canvas.image = photo
            state["rectangle"] = None
            state["image_box"] = (offset_x, offset_y, display_width, display_height)
            orientation = "video doc" if source_height > source_width else "video ngang"
            quality = f"{source_height}p" if source_height >= source_width else f"{source_width}p"
            video_info.configure(text=f"{source_width} x {source_height} px | {orientation} | {quality} | {fps:.2f} FPS | {duration:.1f}s")
            time_label.configure(text=f"{float(value):.1f}s")

        def request_frame(value):
            # Slider emits many events per second; only decode after the drag pauses.
            if state["preview_after"]:
                window.after_cancel(state["preview_after"])
            state["preview_after"] = window.after(80, lambda: show_frame(value))

        def close_preview():
            preview_capture.release()
            window.destroy()

        def clamp_point(event):
            offset_x, offset_y, display_width, display_height = state["image_box"]
            return (
                min(max(event.x, offset_x), offset_x + display_width),
                min(max(event.y, offset_y), offset_y + display_height),
            )

        def save_selection(coords):
            offset_x, offset_y, width, height = state["image_box"]
            x1, y1, x2, y2 = coords
            left, right = sorted(((x1 - offset_x) / width, (x2 - offset_x) / width))
            top, bottom = sorted(((y1 - offset_y) / height, (y2 - offset_y) / height))
            state["selection"] = (left, top, right, bottom)

        def on_press(event):
            if not state["image_box"]:
                return
            x, y = clamp_point(event)
            state["start"] = (x, y)
            state["action"] = "new"
            state["original"] = None
            if state["rectangle"]:
                x1, y1, x2, y2 = canvas.coords(state["rectangle"])
                margin = 12
                if x1 - margin <= x <= x2 + margin and y1 - margin <= y <= y2 + margin:
                    horizontal = "left" if abs(x - x1) < margin else "right" if abs(x - x2) < margin else ""
                    vertical = "top" if abs(y - y1) < margin else "bottom" if abs(y - y2) < margin else ""
                    state["action"] = horizontal + vertical or "move"
                    state["original"] = (x1, y1, x2, y2)
                    return
            state["rectangle"] = canvas.create_rectangle(x, y, x, y, outline="#37d67a", width=3)

        def on_drag(event):
            if not state["start"] or not state["rectangle"]:
                return
            x, y = clamp_point(event)
            action = state["action"]
            if action == "new":
                canvas.coords(state["rectangle"], *state["start"], x, y)
                return
            x1, y1, x2, y2 = state["original"]
            dx, dy = x - state["start"][0], y - state["start"][1]
            offset_x, offset_y, width, height = state["image_box"]
            if action == "move":
                dx = min(max(dx, offset_x - x1), offset_x + width - x2)
                dy = min(max(dy, offset_y - y1), offset_y + height - y2)
                canvas.coords(state["rectangle"], x1 + dx, y1 + dy, x2 + dx, y2 + dy)
            else:
                if "left" in action: x1 = min(x, x2 - 12)
                if "right" in action: x2 = max(x, x1 + 12)
                if "top" in action: y1 = min(y, y2 - 12)
                if "bottom" in action: y2 = max(y, y1 + 12)
                canvas.coords(state["rectangle"], x1, y1, x2, y2)

        def on_release(event):
            if not state["start"]:
                return
            save_selection(canvas.coords(state["rectangle"]))
            state["start"] = None
            state["action"] = None
            state["original"] = None

        def apply_selection():
            region = state["selection"]
            if not region or region[2] - region[0] < 0.02 or region[3] - region[1] < 0.02:
                messagebox.showwarning("Chua chon vung", "Hay keo chuot khoanh vung phu de truoc.", parent=window)
                return
            self.subtitle_region = region
            self.roi_status.set("Vung sub da chon - se ap dung cho toan bo video trong thu muc")
            close_preview()

        slider.configure(command=request_frame)
        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        ctk.CTkButton(window, text="Ap dung vung da khoanh", command=apply_selection, fg_color="green").pack(pady=8)
        window.protocol("WM_DELETE_WINDOW", close_preview)
        show_frame(0)

    @staticmethod
    def _get_video_rotation(video_path, capture):
        """Return the orientation embedded in the video, never a user-chosen rotation."""
        rotation = int(capture.get(getattr(cv2, "CAP_PROP_ORIENTATION_META", 48)) or 0) % 360
        if rotation:
            return rotation
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream_tags=rotate:stream_side_data", "-of", "json", video_path],
                capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            stream = json.loads(result.stdout).get("streams", [{}])[0]
            rotation = stream.get("tags", {}).get("rotate")
            if rotation is not None:
                return int(float(rotation)) % 360
            for item in stream.get("side_data_list", []):
                if "rotation" in item:
                    return int(float(item["rotation"])) % 360
        except (FileNotFoundError, ValueError, KeyError, IndexError, json.JSONDecodeError):
            pass
        return 0
        
    def log(self, message):
        def _update():
            self.log_text.configure(state="normal")
            self.log_text.insert("end", message + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
            self.update_idletasks()
        self.after(0, _update)

    def toggle_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.btn_pause.configure(text="TẠM DỪNG")
            self.log("▶ Đã tiếp tục tiến trình.")
        else:
            self.pause_event.set()
            self.btn_pause.configure(text="TIẾP TỤC")
            self.log("⏸ Đã tạm dừng! (Tool sẽ tạm nghỉ trước khi chuyển sang bước tiếp theo).")

    def wait_if_paused(self):
        import time
        while self.pause_event.is_set() and not self.stop_event.is_set():
            time.sleep(1)

    def start_process(self):
        if not self.input_dir.get() or not self.output_dir.get():
            messagebox.showwarning("Lỗi", "Vui lòng chọn thư mục đầu vào và đầu ra!")
            return
            
        self.is_running = True
        self.stop_event.clear()
        self.pause_event.clear()
        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="normal", text="TẠM DỪNG")
        self.btn_stop.configure(state="normal")
        self.log_text.configure(state="normal")
        self.log_text.delete("0.0", "end")
        self.log_text.configure(state="disabled")
        
        # Chạy trong luồng riêng để không treo GUI
        thread = threading.Thread(target=self.process_batch, daemon=True)
        thread.start()
        
    def stop_process(self):
        self.is_running = False
        self.stop_event.set()
        self.log("Đang yêu cầu dừng... Vui lòng chờ tác vụ hiện tại kết thúc.")
        self.btn_stop.configure(state="disabled")

    def sanitize_filename(self, name):
        # Dọn dẹp chuỗi để làm tên thư mục hợp lệ
        # Xóa triệt để tiếng Trung và dấu câu tiếng Trung
        name = re.sub(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+', '', name)
        name = re.sub(r'[\\/*?:"<>|]', "", name)
        name = name.replace("\n", " ").strip()
        name = re.sub(r' +', ' ', name) # Xóa khoảng trắng thừa
        # Lấy khoảng 10 từ đầu tiên
        words = name.split()[:10]
        # Xóa các dấu chấm (.) hoặc dấu cách ở cuối câu (Windows không cho phép thư mục/file kết thúc bằng dấu chấm)
        clean_name = " ".join(words).rstrip('.… ')
        return clean_name

    def extract_clean_text(self, srt_text):
        # Lấy một đoạn text sạch từ SRT để đặt tên (Bỏ số thứ tự và timestamp)
        lines = srt_text.split('\n')
        clean_lines = [l.strip() for l in lines if not l.strip().isdigit() and '-->' not in l and l.strip()]
        
        # Bỏ qua các từ khóa rác do ChatGPT thỉnh thoảng sinh ra hoặc câu quá ngắn
        ignore_phrases = ["đang suy nghĩ", "dưới đây là", "bản dịch", "chắc chắn", "đây là", "tất nhiên", "phụ đề"]
        
        for line in clean_lines:
            lower_line = line.lower()
            if len(line) < 4:  # Bỏ qua câu quá ngắn
                continue
            if any(phrase in lower_line for phrase in ignore_phrases):
                continue
            return line # Trả về câu hợp lệ đầu tiên
            
        if clean_lines:
            return clean_lines[0]
            
        return "Video"

    def process_batch(self):
        try:
            in_dir = self.input_dir.get()
            out_dir = self.output_dir.get()
            prompt = self.prompt_text.get("0.0", "end").strip()
            
            videos = [f for f in os.listdir(in_dir) if f.lower().endswith(('.mp4', '.mkv', '.avi', '.mov'))]
            if not videos:
                self.log("Không tìm thấy video nào trong thư mục đầu vào.")
                self.reset_ui()
                return
                
            total = len(videos)
            self.log(f"Tìm thấy {total} video cần xử lý.")
            
            orientation = {"Tu dong": "auto", "Doc": "portrait", "Ngang": "landscape"}[self.video_orientation.get()]
            chatgpt = ChatGPTAutomator()
            processor = VideoProcessor(subtitle_region=self.subtitle_region, orientation=orientation)
            
            for i, video_file in enumerate(videos):
                self.wait_if_paused()
                if self.stop_event.is_set():
                    self.log("Đã dừng tiến trình!")
                    break
                    
                video_path = os.path.join(in_dir, video_file)
                self.log(f"\n[{i+1}/{total}] Đang xử lý: {video_file}")
                
                # Bước 1: OCR phụ đề cứng trên khung hình video
                try:
                    srt_content = processor.extract_subtitles_from_video(
                        video_path,
                        log_callback=self.log,
                        stop_event=self.stop_event,
                        pause_event=self.pause_event
                    )
                except Exception as ocr_err:
                    self.log(f"Lỗi khi OCR video {video_file}: {str(ocr_err)}")
                    continue
                    
                if self.stop_event.is_set():
                    self.log("Đã dừng tiến trình!")
                    break
                    
                if not srt_content or not srt_content.strip():
                    self.log("Không trích xuất được âm thanh/thoại nào. Bỏ qua.")
                    continue
                    
                # Bước 2: Dịch qua Cốc Cốc
                self.wait_if_paused()
                if self.stop_event.is_set(): break
                translated_srt, err = chatgpt.translate_srt(prompt, srt_content, self.log)
                if err:
                    self.log(f"Lỗi dịch thuật: {err}")
                    continue
                    
                # Xử lý tiếng Trung triệt để trong kịch bản SRT
                translated_srt = re.sub(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+', '', translated_srt)
                translated_srt = '\n'.join([re.sub(r' +', ' ', line).strip() for line in translated_srt.split('\n')])
                translated_srt = re.sub(r'\n{3,}', '\n\n', translated_srt)
                    
                # Bước 3: Đặt tên thư mục
                folder_name = self.sanitize_filename(self.extract_clean_text(translated_srt))
                if not folder_name:
                    folder_name = self.sanitize_filename(os.path.splitext(video_file)[0])
                    if not folder_name:
                        folder_name = f"Video_{i+1}"
                    
                target_folder = os.path.join(out_dir, folder_name)
                # Đảm bảo tên thư mục không trùng
                counter = 1
                orig_folder_name = target_folder
                while os.path.exists(target_folder):
                    target_folder = f"{orig_folder_name} ({counter})"
                    counter += 1
                os.makedirs(target_folder)
                
                # Bước 4: Lưu file text (Tiếng Việt)
                txt_path = os.path.join(target_folder, f"{folder_name}.txt")
                with open(txt_path, "w", encoding="utf-8-sig") as f:
                    f.write(translated_srt)
                self.log(f"Đã lưu kịch bản tiếng Việt: {txt_path}")
                
                # Lưu thêm file SRT tiếng Việt
                srt_vi_path = os.path.join(target_folder, f"{folder_name}_vi.srt")
                with open(srt_vi_path, "w", encoding="utf-8-sig") as f:
                    f.write(translated_srt)
                self.log(f"Đã lưu SRT tiếng Việt: {srt_vi_path}")
                
                # Lưu thêm file SRT tiếng Trung gốc
                srt_path = os.path.join(target_folder, f"{folder_name}.srt")
                with open(srt_path, "w", encoding="utf-8-sig") as f:
                    f.write(srt_content)
                self.log(f"Đã lưu kịch bản tiếng Trung: {srt_path}")                
                # Bước 5: Copy video gốc
                ext = os.path.splitext(video_path)[1]
                new_video_path = os.path.join(target_folder, f"{folder_name}{ext}")
                shutil.copy2(video_path, new_video_path)
                self.log(f"Đã copy video: {new_video_path}")

                self.after(0, lambda v=(i + 1) / total: self.progress.set(v))
                
            if hasattr(chatgpt, 'disconnect'):
                chatgpt.disconnect()
            self.log("\nHOÀN THÀNH TOÀN BỘ TIẾN TRÌNH!")
            
        except Exception as e:
            self.log(f"\nLỗi hệ thống: {str(e)}")
        finally:
            self.reset_ui()
            
    def reset_ui(self):
        def _reset():
            self.is_running = False
            self.btn_start.configure(state="normal")
            self.btn_pause.configure(state="disabled", text="TẠM DỪNG")
            self.btn_stop.configure(state="disabled")
        self.after(0, _reset)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = App()
    app.mainloop()

