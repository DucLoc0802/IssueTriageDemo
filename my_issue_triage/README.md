# My Issue Triage

Mini-app minh họa một luồng hoàn chỉnh:

```text
issue input
  -> tool_call
  -> application executes
  -> tool_result
  -> IssueTriage final response
  -> Pydantic validation
```

## Cấu trúc dễ học

Toàn bộ logic chính nằm trong `app.py`, được chia thành bốn phần:

1. `IssueTriage`: schema Pydantic của kết quả cuối.
2. `TOOLS` và `execute_tool()`: khai báo và thực thi tool.
3. `build_messages()` và `run_triage()`: prompt cùng workflow.
4. Phần cuối file: giao diện Streamlit.

## Chạy trên Windows PowerShell

```powershell
cd 'C:\Users\HP\Desktop\tuan2\my_issue_triage'

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

Copy-Item .env.example .env
notepad .env
```

Điền API key, base URL và model ID vào `.env`, sau đó chạy:

```powershell
.\.venv\Scripts\python.exe -m streamlit run .\app.py --server.headless true
```

Mở `http://localhost:8501` và bấm **Phân loại issue**.

Model được chọn phải hỗ trợ cả function calling và structured output.

## Tự học lại theo thứ tự

Không cần học thuộc toàn bộ file. Hãy tự viết lại lần lượt:

1. Viết class `IssueTriage`.
2. Viết dictionary `COMPONENT_OWNERS` và hàm `execute_tool()`.
3. Viết `build_messages()` để tách system instruction với user input.
4. Gọi model lần đầu để lấy tool call.
5. Chạy tool rồi thêm tool result vào messages.
6. Gọi model lần hai với `response_format=IssueTriage`.
7. Cuối cùng mới thêm giao diện Streamlit.

Không đưa `.env`, API key hoặc thư mục `.venv` lên Google Drive.
