from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

import streamlit as st
from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, ConfigDict, Field


APP_DIR = Path(__file__).resolve().parent
load_dotenv(APP_DIR / ".env")


class IssueTriage(BaseModel):
    """Kết quả phân loại cuối cùng mà Gemini bắt buộc phải trả về."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(description="Tóm tắt issue trong một câu")
    severity: Literal["P0", "P1", "P2", "P3"]
    component: Literal["payment", "identity", "search"]
    owner: str = Field(description="Team chịu trách nhiệm")
    reason: str = Field(description="Lý do chọn severity và component")
    suggested_action: str = Field(description="Hành động tiếp theo được đề xuất")


COMPONENT_OWNERS = {
    "payment": "checkout-platform",
    "identity": "identity-platform",
    "search": "search-platform",
}


def get_component_owner(component: str) -> dict[str, str]:
    if component not in COMPONENT_OWNERS:
        raise ValueError(f"Component không hợp lệ: {component}")

    return {
        "component": component,
        "owner": COMPONENT_OWNERS[component],
    }


GET_COMPONENT_OWNER_TOOL = {
    "type": "function",
    "name": "get_component_owner",
    "description": "Tìm team chịu trách nhiệm cho một component phần mềm.",
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
}

AVAILABLE_FUNCTIONS = {
    "get_component_owner": get_component_owner,
}

INSTRUCTION = """Bạn là trợ lý phân loại issue phần mềm.

Nhiệm vụ:
- xác định severity theo P0/P1/P2/P3;
- xác định component là payment, identity hoặc search;
- bắt buộc gọi get_component_owner để tìm team phụ trách;
- owner phải lấy từ kết quả của tool;
- không tự bịa owner;
- chỉ sử dụng thông tin từ issue người dùng cung cấp.

Ý nghĩa severity:
- P0: hệ thống hoặc chức năng quan trọng bị ngừng hoàn toàn, ảnh hưởng nghiêm trọng.
- P1: lỗi nghiêm trọng, ảnh hưởng nhiều người dùng hoặc chức năng chính.
- P2: lỗi mức trung bình, vẫn có thể tiếp tục sử dụng hệ thống.
- P3: lỗi nhỏ, ít ảnh hưởng hoặc chủ yếu liên quan trải nghiệm.
"""


def execute_tool(function_call: Any) -> dict[str, Any]:
    """Kiểm tra yêu cầu của model trước khi thực thi hàm Python."""

    function = AVAILABLE_FUNCTIONS.get(function_call.name)
    if function is None:
        raise ValueError(f"Tool không được hỗ trợ: {function_call.name}")

    arguments = dict(function_call.arguments or {})
    if set(arguments) != {"component"}:
        raise ValueError("Tool phải nhận đúng một tham số component.")

    return function(**arguments)


def run_triage(issue: str) -> tuple[IssueTriage, list[dict[str, Any]]]:
    """Chạy function calling, structured output và validation đầu-cuối."""

    issue = issue.strip()
    if not issue:
        raise ValueError("Mô tả issue không được để trống.")

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Thiếu GEMINI_API_KEY hoặc GOOGLE_API_KEY trong file .env.")

    model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()
    if not model:
        raise RuntimeError("GEMINI_MODEL không được để trống.")

    client = genai.Client(api_key=api_key)
    trace: list[dict[str, Any]] = []

    try:
        interaction = client.interactions.create(
            model=model,
            system_instruction=INSTRUCTION,
            input=issue,
            tools=[GET_COMPONENT_OWNER_TOOL],
            generation_config={"tool_choice": "any"},
        )

        function_call = next(
            (step for step in interaction.steps if step.type == "function_call"),
            None,
        )
        if function_call is None:
            raise RuntimeError("Model không gọi get_component_owner.")

        arguments = dict(function_call.arguments or {})
        trace.append(
            {
                "stage": "tool_call",
                "data": {"name": function_call.name, "arguments": arguments},
            }
        )
        trace.append(
            {
                "stage": "application executes",
                "data": "Ứng dụng kiểm tra tên tool và arguments rồi thực thi hàm Python.",
            }
        )

        tool_data = execute_tool(function_call)
        trace.append({"stage": "tool_result", "data": tool_data})

        function_result = {
            "type": "function_result",
            "name": function_call.name,
            "call_id": function_call.id,
            "result": [
                {
                    "type": "text",
                    "text": json.dumps(tool_data, ensure_ascii=False),
                }
            ],
        }

        final_interaction = client.interactions.create(
            model=model,
            input=[function_result],
            previous_interaction_id=interaction.id,
            response_format=[
                {
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": IssueTriage.model_json_schema(),
                }
            ],
        )

        if not final_interaction.output_text:
            raise RuntimeError("Model không trả về kết quả cuối cùng.")

        triage = IssueTriage.model_validate_json(final_interaction.output_text)

        if triage.component != tool_data["component"]:
            raise ValueError("Component của kết quả cuối không khớp tool result.")
        if triage.owner != tool_data["owner"]:
            raise ValueError("Owner của kết quả cuối không khớp tool result.")

        trace.append({"stage": "final response", "data": triage.model_dump()})
        return triage, trace
    finally:
        client.close()


def render_app() -> None:
    st.set_page_config(page_title="Issue Triage", layout="wide")
    st.title("Issue Triage Mini-App")
    st.caption("Structured Output · Function Calling · Application Validation")

    issue = st.text_area(
        "Mô tả issue",
        value="Nút thanh toán trả HTTP 500 với mọi thẻ Visa từ 14:30.",
        height=150,
    )

    if not st.button("Phân loại issue", type="primary", use_container_width=True):
        return

    if not issue.strip():
        st.warning("Hãy nhập mô tả issue.")
        return

    try:
        with st.spinner("Đang phân loại issue..."):
            triage, trace = run_triage(issue)

        st.success("Phân loại và validate thành công.")
        left, right = st.columns(2)

        with left:
            st.subheader("IssueTriage")
            st.json(triage.model_dump())

        with right:
            st.subheader("Workflow Trace")
            for index, item in enumerate(trace, start=1):
                with st.expander(f"{index}. {item['stage']}", expanded=True):
                    if isinstance(item["data"], dict):
                        st.json(item["data"])
                    else:
                        st.write(item["data"])
    except Exception as error:
        st.error(f"Không chạy được: {error}")
        st.info("Kiểm tra API key, model trong .env và kết nối Internet.")


if __name__ == "__main__":
    render_app()
