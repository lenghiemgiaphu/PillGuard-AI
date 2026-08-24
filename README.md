# PillGuard AI — hướng dẫn chạy sau khi gộp

## 1. Những gì đã sửa trong bản gộp này

- `ocr_engine.py`: sửa lỗi hàm `process_handwriting_ocr` nhận `api_key` làm tham số
  nhưng lại bỏ qua, dùng thẳng key gắn cứng trong code. Giờ đã dùng đúng `api_key`
  được truyền vào.
- `gemini_ai.py`: **file này bị thiếu** trong bản `app.py` gốc bạn của bạn gửi —
  `app.py` có `from gemini_ai import check_drug_interaction` nhưng không có file
  `gemini_ai.py` đi kèm, nên route `/api/check-ddi` sẽ báo lỗi `NameError` khi gọi.
  Đã viết lại file này.
- `app.py`: gộp 2 server riêng biệt (`app.py` cũ chạy OCR+DDI ở cổng 5000, và
  `server.py` chạy giọng nói ở cổng 8000) thành **một server Flask duy nhất** ở
  cổng 5000, có đủ cả 4 API: `/api/ocr`, `/api/check-ddi`, `/speech-to-text`,
  `/process-message`. Lý do: file `script.js` phía Front-End gọi
  `baseUrl = window.location.origin` — nếu chạy 2 server ở 2 cổng khác nhau,
  các lệnh gọi giọng nói sẽ bị lỗi 404 vì trang được phục vụ từ cổng 5000 nhưng
  các route giọng nói lại chỉ tồn tại ở cổng 8000.

## 2. Việc BẮT BUỘC phải làm trước khi chạy

**Thu hồi (revoke) ngay API key Gemini đã lộ** (`AQ.Ab8RN6JS2...`) — key này đã
xuất hiện lặp lại trong nhiều file (`Run.py`, `app.py`, `ocr_engine.py`) gửi qua
nhiều lượt chat, nghĩa là nó chưa được thu hồi. Vào Google AI Studio, revoke key
cũ, tạo key mới, và **không** dán trực tiếp vào code nữa.

## 3. Cài đặt

```bash
pip install -r requirements.txt
```

Đặt biến môi trường (thay bằng key MỚI, không dùng key cũ đã lộ):

```bash
# macOS/Linux
export GEMINI_API_KEY="key_gemini_moi_cua_ban"
export OPENAI_API_KEY="key_openai_moi_cua_ban"

# Windows PowerShell
$env:GEMINI_API_KEY="key_gemini_moi_cua_ban"
$env:OPENAI_API_KEY="key_openai_moi_cua_ban"
```

## 4. Sắp xếp file

Copy `app.py`, `ocr_engine.py`, `gemini_ai.py`, `worker.py`, `requirements.txt`
vào cùng thư mục gốc dự án Front-End (nơi có sẵn 2 thư mục `templates/` và
`static/` từ `DU-AN-main`). `app.py` cần `templates/index.html` để chạy
`render_template("index.html")`.

## 5. Chạy

```bash
python app.py
```

Mở trình duyệt tại `http://127.0.0.1:5000`.

## 6. Lưu ý an toàn quan trọng về DDI

`gemini_ai.py` hiện chỉ hỏi thẳng Gemini, **không đối chiếu với cơ sở dữ liệu
dược lý chính thức** (dù bạn đã có sẵn `thuoc_data.csv.gz` từ việc scrape
dav.gov.vn — dữ liệu này hiện chưa được dùng để kiểm chứng). Vì đối tượng dùng
là người già, **nên có dược sĩ/bác sĩ kiểm duyệt** nội dung cảnh báo trước khi
đưa vào sử dụng thật, đặc biệt với các trường hợp AI báo "AN TOÀN".
