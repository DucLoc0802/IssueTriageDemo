from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field


# -----------------------------------------------------------------------------
# 1. Cấu trúc kết quả cuối cùng
# -----------------------------------------------------------------------------


class IssueTriage(BaseModel):
    """Schema mà câu trả lời cuối của model bắt buộc phải tuân theo."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(description="Tóm tắt issue trong một câu")
    severity: Literal["P0", "P1", "P2", "P3"]
    component: Literal["payment", "identity", "search"]
    owner: str = Field(description="Team chịu trách nhiệm")
    reason: str = Field(description="Lý do chọn severity và component")
    suggested_action: str = Field(description="Hành động tiếp theo được đề xuất")


# -----------------------------------------------------------------------------
# 2. Tool do application sở hữu
# -----------------------------------------------------------------------------

COMPONENT_OWNERS = {
    "payment": "checkout-platform",
    "identity": "identity-platform",
    "search": "search-platform",
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_component_owner",
            "description": "Tìm team phụ trách một component phần mềm.",
            "parameters": {
                "type": "object",
                "properties": {
                    "component": {
                        "type": "string",
                        "enum": list(COMPONENT_OWNERS),
                    }
                },
                "required": ["component"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
]


def execute_tool(tool_name: str, raw_arguments: str) -> dict[str, str]:
    """Validate yêu cầu của model trước khi application chạy tool."""

    if tool_name != "get_component_owner":
        raise ValueError(f"Tool không được phép: {tool_name}")

    arguments = json.loads(raw_arguments)
    if not isinstance(arguments, dict) or set(arguments) != {"component"}:
        raise ValueError("Tool phải nhận đúng một tham số component.")

    component = arguments["component"]
    if component not in COMPONENT_OWNERS:
        raise ValueError(f"Component không hợp lệ: {component}")

    return {
        "component": component,
        "owner": COMPONENT_OWNERS[component],
    }


# -----------------------------------------------------------------------------
# 3. Prompt và workflow
# -----------------------------------------------------------------------------

INSTRUCTION = """Bạn là trợ lý phân loại issue phần mềm.
Hãy xác định severity theo P0/P1/P2/P3 và component phù hợp.
Bạn phải gọi get_component_owner để biết team chịu trách nhiệm.
Chỉ kết luận từ dữ liệu trong phần INPUT; không tự bịa thêm sự kiện."""


def build_messages(issue: str) -> list[Any]:
    """Tách instruction và input thành hai message riêng biệt."""

    return [
        {"role": "system", "content": INSTRUCTION},
        {"role": "user", "content": f"INPUT:\n{issue}"},
    ]


def run_triage(issue: str) -> tuple[IssueTriage, list[dict[str, Any]]]:
    """Chạy toàn bộ flow và trả kết quả cùng trace để hiển thị."""

    load_dotenv(Path(__file__).with_name(".env"))
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("OPENAI_MODEL")

    if not api_key or not base_url or not model:
        raise RuntimeError("Thiếu OPENAI_API_KEY, OPENAI_BASE_URL hoặc OPENAI_MODEL trong .env")

    client = OpenAI(api_key=api_key, base_url=base_url)
    messages = build_messages(issue)
    trace: list[dict[str, Any]] = []

    # Lần gọi 1: model chỉ đề xuất tool; application chưa tự động tin kết quả này.
    first_response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=TOOLS,
        tool_choice="required",
    )
    assistant_message = first_response.choices[0].message
    tool_calls = assistant_message.tool_calls or []
    if not tool_calls:
        raise RuntimeError("Model không yêu cầu gọi tool.")

    messages.append(assistant_message)
    executed_results: list[dict[str, str]] = []

    for tool_call in tool_calls:
        arguments = json.loads(tool_call.function.arguments)
        trace.append(
            {
                "stage": "tool_call",
                "data": {
                    "name": tool_call.function.name,
                    "arguments": arguments,
                },
            }
        )

        trace.append(
            {
                "stage": "application executes",
                "data": "Application đang validate tên tool và arguments",
            }
        )
        tool_result = execute_tool(
            tool_call.function.name,
            tool_call.function.arguments,
        )
        executed_results.append(tool_result)
        trace.append({"stage": "tool_result", "data": tool_result})

        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(tool_result, ensure_ascii=False),
            }
        )

    # Lần gọi 2: ép câu trả lời cuối tuân theo schema IssueTriage.
    final_response = client.beta.chat.completions.parse(
        model=model,
        messages=messages,
        response_format=IssueTriage,
    )
    parsed = final_response.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError("Model không trả về IssueTriage hợp lệ.")

    # Validate ở phía application, không chỉ tin dữ liệu model trả về.
    result = IssueTriage.model_validate(parsed.model_dump())
    expected_owner = COMPONENT_OWNERS[result.component]
    if result.owner != expected_owner:
        raise ValueError(
            f"Owner không khớp tool result: mong đợi {expected_owner}, nhận {result.owner}"
        )
    if not any(item == {"component": result.component, "owner": result.owner} for item in executed_results):
        raise ValueError("Kết quả cuối không khớp với tool đã được application thực thi.")

    trace.append({"stage": "final response", "data": result.model_dump()})
    return result, trace


# -----------------------------------------------------------------------------
# 4. Giao diện Streamlit
# -----------------------------------------------------------------------------

st.set_page_config(page_title="My Issue Triage", page_icon="🔎", layout="wide")
st.title("Issue Triage mini-app")
st.caption("Structured Output · Application Validation · Function Calling")

issue = st.text_area(
    "Mô tả issue",
    value="Nút thanh toán trả HTTP 500 với mọi thẻ Visa từ 14:30.",
    height=150,
)

if st.button("Phân loại issue", type="primary", use_container_width=True):
    if not issue.strip():
        st.warning("Hãy nhập mô tả issue.")
    else:
        try:
            with st.spinner("Đang phân loại..."):
                triage, workflow_trace = run_triage(issue.strip())

            st.success("Đã phân loại và validate kết quả thành công.")

            left, right = st.columns(2)
            with left:
                st.subheader("IssueTriage")
                st.json(triage.model_dump())

            with right:
                st.subheader("Workflow trace")
                for number, item in enumerate(workflow_trace, start=1):
                    with st.expander(f"{number}. {item['stage']}", expanded=True):
                        if isinstance(item["data"], dict):
                            st.json(item["data"])
                        else:
                            st.write(item["data"])
        except Exception as error:
            st.error(f"Không chạy được demo: {error}")
            st.info("Kiểm tra lại .env và khả năng hỗ trợ tool/structured output của model.")
