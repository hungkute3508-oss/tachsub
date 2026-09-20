import time
import re
from playwright.sync_api import sync_playwright

class BaseAIAutomator:
    """Lớp cơ sở điều khiển trình duyệt Cốc Cốc qua CDP để tự động hóa dịch SRT bằng AI."""

    def __init__(self, ai_name, target_urls, input_selectors, send_selectors, assistant_selectors, error_selectors, cdp_port=9223):
        self.ai_name = ai_name
        self.target_urls = target_urls
        self.input_selectors = input_selectors
        self.send_selectors = send_selectors
        self.assistant_selectors = assistant_selectors
        self.error_selectors = error_selectors
        self.cdp_url = f"http://127.0.0.1:{cdp_port}"
        self.playwright = None
        self.browser = None

    def connect(self, log_callback=None):
        if not self.playwright:
            if log_callback:
                log_callback("Đang khởi tạo kết nối Playwright...")
            self.playwright = sync_playwright().start()
        if not self.browser:
            if log_callback:
                log_callback("Đang kết nối vào Cốc Cốc qua cổng 9223...")
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
        for sel in self.assistant_selectors:
            try:
                loc = chat_page.locator(sel)
                if loc.count() > 0:
                    return loc
            except Exception:
                continue
        return None

    def _is_generating(self, chat_page):
        return False

    def _clean_srt_output(self, text):
        if "[START SRT]" in text and "[END SRT]" in text:
            match = re.search(r'\[START SRT\](.*?)\[END SRT\]', text, re.DOTALL)
            if match:
                return match.group(1).strip()
        match = re.search(r'```(?:srt)?\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()

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
                    if any(target in page.url for target in self.target_urls):
                        chat_page = page
                        break
                if chat_page:
                    break

            if not chat_page:
                return None, (
                    f"Không tìm thấy tab {self.ai_name} nào đang mở trên Cốc Cốc. "
                    f"Hãy mở sẵn tab {self.target_urls[0]} và thử lại."
                )

            log(f"Đã kết nối tab {self.ai_name} thành công. Đang gửi kịch bản...")
            full_message = f"{prompt}\n\n[START SRT]\n{srt_content}\n[END SRT]"

            # Tìm ô nhập văn bản
            chat_input = None
            for sel in self.input_selectors:
                loc = chat_page.locator(sel)
                if loc.count() > 0:
                    chat_input = loc.first
                    break

            if not chat_input:
                return None, f"Không tìm thấy ô nhập tin nhắn trên giao diện {self.ai_name}."

            chat_input.click()
            time.sleep(0.3)
            chat_page.keyboard.insert_text(full_message)
            time.sleep(1)

            # Bấm gửi
            sent = False
            for sel in self.send_selectors:
                btn = chat_page.locator(sel).first
                if btn.is_visible() and btn.is_enabled():
                    btn.click()
                    sent = True
                    break
            if not sent:
                chat_input.press("Enter")

            log(f"Đã gửi yêu cầu tới {self.ai_name}. Đang theo dõi tiến trình sinh văn bản...")
            time.sleep(2)

            last_text = ""
            unchanged_count = 0
            start_time = time.time()
            last_status_log = time.time()

            for second in range(1, 301):
                time.sleep(1)
                elapsed = int(time.time() - start_time)

                # Kiểm tra lỗi
                for err_sel in self.error_selectors:
                    err_loc = chat_page.locator(err_sel)
                    if err_loc.count() > 0 and err_loc.first.is_visible():
                        err_msg = err_loc.first.inner_text().strip()
                        if 0 < len(err_msg) < 200:
                            return None, f"{self.ai_name} thông báo lỗi: {err_msg}"

                loc = self._find_assistant_messages(chat_page)
                if loc and loc.count() > 0:
                    current_count = loc.count()
                    current_text = loc.nth(current_count - 1).inner_text().strip()

                    if current_text:
                        if current_text == last_text:
                            unchanged_count += 1
                        else:
                            unchanged_count = 0
                            last_text = current_text

                        if time.time() - last_status_log >= 5.0:
                            char_len = len(current_text)
                            line_count = current_text.count("\n") + 1
                            log(f"[{self.ai_name}] Đang viết kịch bản ({elapsed}s) | Nhận được {char_len} ký tự (~{line_count} dòng)...")
                            last_status_log = time.time()

                        is_generating = self._is_generating(chat_page)
                        if ((unchanged_count >= 4) or (not is_generating and unchanged_count >= 2)) and len(current_text) > 30:
                            clean_text = self._clean_srt_output(current_text)
                            log(f"✓ {self.ai_name} đã hoàn thành sau {elapsed}s.")
                            return clean_text, None
                else:
                    if time.time() - last_status_log >= 5.0:
                        log(f"[{self.ai_name}] Đang chờ phản hồi... ({elapsed}s)")
                        last_status_log = time.time()

            if last_text:
                return self._clean_srt_output(last_text), None
            return None, f"Hết thời gian chờ (5 phút) nhưng không nhận được phản hồi từ {self.ai_name}."

        except Exception as e:
            err_str = str(e)
            if "ECONNREFUSED" in err_str:
                return None, (
                    "Chưa kết nối được với trình duyệt Cốc Cốc qua cổng 9223.\n"
                    "👉 CÁCH KHẮC PHỤC:\n"
                    "1. Hãy tắt hoàn toàn các cửa sổ Cốc Cốc đang mở.\n"
                    "2. Nhấp đúp chạy file 'Run_CocCoc_Debug.bat' để mở Cốc Cốc ở chế độ Debug.\n"
                    f"3. Trên cửa sổ Cốc Cốc vừa hiện ra, mở tab '{self.target_urls[0]}' và bấm BẮT ĐẦU lại trên Tool."
                )
            return None, f"Lỗi điều khiển trình duyệt: {err_str}"


class ChatGPTAutomator(BaseAIAutomator):
    def __init__(self, cdp_port=9223):
        super().__init__(
            ai_name="ChatGPT",
            target_urls=["chatgpt.com", "chat.openai.com"],
            input_selectors=['#prompt-textarea', 'div[contenteditable="true"]', 'textarea'],
            send_selectors=[
                '[data-testid="send-button"]',
                'button[aria-label*="Send"]',
                'button[aria-label*="Gửi"]',
                'button[data-testid="fruitjuice-send-button"]'
            ],
            assistant_selectors=[
                'div.agent-turn div[data-message-author-role="assistant"]',
                'article[data-testid^="conversation-turn-"] div[data-message-author-role="assistant"]',
                'div[data-message-author-role="assistant"]',
                '[data-message-author-role="assistant"]',
                'article div.markdown',
                'div.markdown'
            ],
            error_selectors=[
                'div[class*="text-red-"]',
                'div.text-token-text-error',
                'div:has-text("There was an error")'
            ],
            cdp_port=cdp_port
        )


class GeminiAutomator(BaseAIAutomator):
    def __init__(self, cdp_port=9223):
        super().__init__(
            ai_name="Gemini",
            target_urls=["gemini.google.com"],
            input_selectors=[
                'div.ql-editor[contenteditable="true"]',
                'rich-textarea div[contenteditable="true"]',
                'div[contenteditable="true"]',
                'p.paragraph',
                'textarea',
                'div.textarea'
            ],
            send_selectors=[
                'button[aria-label*="Gửi tin nhắn"]',
                'button[aria-label*="Send message"]',
                'button[aria-label*="Gửi"]',
                'button[aria-label*="Send"]',
                'button.send-button',
                'button[data-test-id="send-button"]',
                'button:has(mat-icon[data-mat-icon-name="send"])',
                'button:has(mat-icon)'
            ],
            assistant_selectors=[
                'model-response message-content',
                'model-response',
                'message-content',
                'div.model-response-text',
                '.response-container-content',
                '.response-container',
                'div.markdown',
                'div[class*="response-content"]'
            ],
            error_selectors=[
                'div[class*="error"]',
                'div:has-text("Đã xảy ra lỗi")',
                'div:has-text("Something went wrong")'
            ],
            cdp_port=cdp_port
        )

    def _is_generating(self, chat_page):
        stop_btn = chat_page.locator('button[aria-label*="Dừng"], button[aria-label*="Stop"]').first
        return stop_btn.is_visible() if (stop_btn.count() > 0) else False
