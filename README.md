# Issue Triage với Gemini

Ứng dụng Streamlit dùng Gemini để phân loại issue phần mềm theo mức độ ưu tiên, xác định component và tìm team phụ trách bằng function calling.

## Luồng xử lý

```text
Issue người dùng nhập
  -> Gemini yêu cầu gọi get_component_owner
  -> Ứng dụng kiểm tra và thực thi hàm Python
  -> Kết quả của tool được gửi lại cho Gemini
  -> Gemini trả về JSON theo schema IssueTriage
  -> Pydantic kiểm tra dữ liệu cuối cùng
```

Kết quả gồm các trường:

- `summary`: tóm tắt issue;
- `severity`: mức độ `P0`, `P1`, `P2` hoặc `P3`;
- `component`: `payment`, `identity` hoặc `search`;
- `owner`: team phụ trách component;
- `reason`: lý do phân loại;
- `suggested_action`: hành động tiếp theo được đề xuất.

## Yêu cầu

- Python 3.11 trở lên;
- Gemini API key;
- model Gemini hỗ trợ function calling và structured output.

Ứng dụng mặc định sử dụng model `gemini-3.6-flash`. Có thể đổi model bằng biến `GEMINI_MODEL` trong `.env`.

## Cài đặt trên Windows PowerShell

B1: Di chuyển vào thư mục dự án

B2: Tạo môi trường ảo và cài thư viện

```powershell
py -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
```

## Cấu hình

Tạo file `.env` trong cùng thư mục với `App.py`:

```dotenv
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.6-flash
```

## Chạy ứng dụng

```powershell
& ".\.venv\Scripts\python.exe" -m streamlit run ".\App.py"
```

Sau đó mở địa chỉ Streamlit hiển thị trong terminal, mặc định là:

```text
http://localhost:8501
```

Nhấn `Ctrl+C` trong terminal để dừng ứng dụng.

## Lỗi thường gặp

### `ImportError: cannot import name 'genai' from 'google'`

Cài dependency bằng đúng Python của môi trường ảo:

```powershell
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
```

Không cài package có tên `google`; SDK được dự án sử dụng là `google-genai`.

### `missing ScriptRunContext`

Lỗi này xảy ra khi chạy `python App.py`. Hãy khởi động ứng dụng bằng `python -m streamlit run App.py` như hướng dẫn phía trên.

### Không tìm thấy API key

Kiểm tra file `.env` nằm cùng thư mục với `App.py` và có biến `GEMINI_API_KEY` hợp lệ.

## Cấu trúc dự án

```text
IssueTriage/
├── .env
├── .gitignore
├── App.py
├── README.md
└── requirements.txt
```
