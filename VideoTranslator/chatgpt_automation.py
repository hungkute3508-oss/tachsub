import time
from playwright.sync_api import sync_playwright

class ChatGPTAutomator:
    def __init__(self, cdp_port=9223):
        self.cdp_url = f"http://127.0.0.1:{cdp_port}"
        self.playwright = None
        self.browser = None
        
    def connect(self, log_callback=None):
        if not self.playwright:
            if log_callback: log_callback("Đang khởi tạo kết nối Playwright...")
            self.playwright = sync_playwright().start()
        if not self.browser:
            if log_callback: log_callback("Đang kết nối vào Cốc Cốc qua cổng 9223...")
            self.browser = self.playwright.chromium.connect_over_cdp(self.cdp_url)
            
    def disconnect(self):
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
            self.browser = None
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
            self.playwright = None

    def _find_assistant_messages(self, chat_page):
        """Tìm các block phản hồi của ChatGPT với nhiều selector dự phòng."""
        selectors = [
            'div.agent-turn div[data-message-author-role="assistant"]',
            'article[data-testid^="conversation-turn-"] div[data-message-author-role="assistant"]',
            'div[data-message-author-role="assistant"]',
            '[data-message-author-role="assistant"]',
            'article div.markdown',
            'div.markdown'
        ]
        for sel in selectors:
            try:
                loc = chat_page.locator(sel)
                if loc.count() > 0:
                    return loc
            except Exception:
                continue
        return None

    def translate_srt(self, prompt, srt_content, log_callback=None):
        def log(msg):
            if log_callback:
                log_callback(msg)
            else:
                print(msg)
                
        try:
            self.connect(log_callback)
            
            chat_page = None
            for context in self.browser.contexts:
                for page in context.pages:
                    if "chatgpt.com" in page.url or "chat.openai.com" in page.url:
                        chat_page = page
                        break
                if chat_page:
                    break
            
            if not chat_page:
                return None, "Không tìm thấy tab ChatGPT nào đang mở trên Cốc Cốc. Hãy mở tab ChatGPT và thử lại."
            
            log("Đã kết nối tab ChatGPT thành công. Đang gửi kịch bản...")
            
            full_message = f"{prompt}\n\n[START SRT]\n{srt_content}\n[END SRT]"
            
            # Tìm ô nhập văn bản
            input_selectors = ['#prompt-textarea', 'div[contenteditable="true"]', 'textarea']
            chat_input = None
            for sel in input_selectors:
                loc = chat_page.locator(sel)
                if loc.count() > 0:
                    chat_input = loc.first
                    break
                    
            if not chat_input:
                return None, "Không tìm thấy ô nhập tin nhắn trên giao diện ChatGPT."
            
            chat_input.click()
            chat_page.keyboard.insert_text(full_message)
            time.sleep(1) # Chờ UI cập nhật
            
            # Bấm gửi
            send_selectors = [
                '[data-testid="send-button"]',
                'button[aria-label*="Send"]',
                'button[aria-label*="Gửi"]',
                'button[data-testid="fruitjuice-send-button"]'
            ]
            sent = False
            for sel in send_selectors:
                btn = chat_page.locator(sel).first
                if btn.is_visible() and btn.is_enabled():
                    btn.click()
                    sent = True
                    break
            if not sent:
                chat_input.press("Enter")
            
            log("Đã gửi yêu cầu tới ChatGPT. Đang theo dõi tiến trình sinh văn bản...")
            time.sleep(2)
            
            # Đếm số phản hồi ban đầu để biết câu trả lời mới
            initial_loc = self._find_assistant_messages(chat_page)
            initial_count = initial_loc.count() if initial_loc else 0
            
            last_text = ""
            unchanged_count = 0
            start_time = time.time()
            last_status_log = time.time()
            
            for second in range(1, 301): # Tối đa 5 phút
                time.sleep(1)
                elapsed = int(time.time() - start_time)
                
                # Kiểm tra lỗi mạng / nút regenerate / lỗi quota
                error_loc = chat_page.locator('div[class*="text-red-"], div.text-token-text-error, div:has-text("There was an error")')
                if error_loc.count() > 0 and error_loc.first.is_visible():
                    err_msg = error_loc.first.inner_text()
                    return None, f"ChatGPT thông báo lỗi: {err_msg}"

                loc = self._find_assistant_messages(chat_page)
                if loc and loc.count() > 0:
                    current_count = loc.count()
                    # Lấy tin nhắn mới nhất
                    current_text = loc.nth(current_count - 1).inner_text().strip()
                    
                    if current_text:
                        if current_text == last_text:
                            unchanged_count += 1
                        else:
                            unchanged_count = 0
                            last_text = current_text
                            
                        # Log tiến độ sinh chữ mỗi 5 giây
                        if time.time() - last_status_log >= 5.0:
                            char_len = len(current_text)
                            line_count = current_text.count("\n") + 1
                            log(f"[ChatGPT] Đang viết kịch bản ({elapsed}s) | Nhận được {char_len} ký tự (~{line_count} dòng)...")
                            last_status_log = time.time()

                        # Nếu nội dung không thay đổi trong 4 giây liên tiếp và đã có nội dung -> Xong
                        if unchanged_count >= 4 and len(current_text) > 30:
                            log(f"✓ ChatGPT đã hoàn thành sau {elapsed}s.")
                            return current_text, None
                else:
                    if time.time() - last_status_log >= 5.0:
                        log(f"[ChatGPT] Đang chờ ChatGPT bắt đầu phản hồi... ({elapsed}s)")
                        last_status_log = time.time()
            
            if last_text:
                return last_text, None
            return None, "Hết thời gian chờ (5 phút) nhưng không nhận được phản hồi từ ChatGPT."

        except Exception as e:
            return None, f"Lỗi điều khiển trình duyệt: {str(e)}\n\nHãy đảm bảo bạn đã mở Cốc Cốc với tham số --remote-debugging-port=9223"
