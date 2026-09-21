import json
import streamlit as st
from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, Field
from typing import Literal

load_dotenv()

class IssueTriage(BaseModel):
    summary: str = Field(description="Tóm tắt issue trong một câu")
    severity: Literal["P0", "P1", "P2", "P3"]
    component: Literal["payment", "identity", "search"]
    owner: str = Field(description="Team chịu trách nhiệm")
    reason: str = Field(description="Lý do chọn severity và component")
    suggested_action: str = Field(description="Hành động tiếp theo được đề xuất")

COMPONENT_OWNERS = {
    "payment": "checkout-platform",
    "identity": "identity-platform",
    "search": "search-platform"
}

def get_component_owner(component: str):
    if component not in COMPONENT_OWNERS:
        raise ValueError(f"Component không hợp lệ: {component}")

    return {
        "component": component,
        "owner": COMPONENT_OWNERS[component]
    }

get_component_owner_tool = {
    "type": "function",
    "name": "get_component_owner",
    "description": "Tìm team chịu trách nhiệm cho một component phần mềm.",
    "parameters": {
        "type": "object",
        "properties": {
            "component": {
                "type": "string",
                "enum": ["payment", "identity", "search"]
            }
        },
        "required": ["component"]
    }
}

available_functions = {
    "get_component_owner": get_component_owner
}

available_tools = [
    get_component_owner_tool
]

INSTRUCTION = """
Bạn là trợ lý phân loại issue phần mềm.

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

def execute_tool(function_call):
    function = available_functions.get(function_call.name)

    if function is None:
        return {
            "success": False,
            "error": f"Unknown tool: {function_call.name}"
        }

    try:
        result = function(**function_call.arguments)

        return {
            "success": True,
            "data": result
        }

    except Exception as error:
        return {
            "success": False,
            "error": str(error)
        }

def run_triage(issue: str):
    client = genai.Client()
    trace = []

    interaction = client.interactions.create(
        model="gemini-3.6-flash",
        system_instruction=INSTRUCTION,
        input=issue,
        tools=available_tools,
        generation_config={
            "tool_choice": "any"
        }
    )

    function_call = None

    for step in interaction.steps:
        if step.type == "function_call":
            function_call = step
            break

    if function_call is None:
        raise RuntimeError("Model không gọi tool.")

    trace.append({
        "stage": "tool_call",
        "data": {
            "name": function_call.name,
            "arguments": function_call.arguments
        }
    })

    trace.append({
        "stage": "application executes",
        "data": "Application kiểm tra tên tool, arguments và tự thực thi Python function."
    })

    result = execute_tool(function_call)

    trace.append({
        "stage": "tool_result",
        "data": result
    })

    if not result["success"]:
        raise ValueError(f"Tool chạy thất bại: {result['error']}")

    function_result = {
        "type": "function_result",
        "name": function_call.name,
        "call_id": function_call.id,
        "result": [
            {
                "type": "text",
                "text": json.dumps(result, ensure_ascii=False)
            }
        ]
    }

    final_interaction = client.interactions.create(
        model="gemini-3.6-flash",
        input=[function_result],
        previous_interaction_id=interaction.id,
        response_format=[
            {
                "type": "text",
                "mime_type": "application/json",
                "schema": IssueTriage.model_json_schema()
            }
        ]
    )

    triage = IssueTriage.model_validate_json(
        final_interaction.output_text
    )

    tool_data = result["data"]

    if triage.component != tool_data["component"]:
        raise ValueError(
            "Component của final response không khớp tool result."
        )

    if triage.owner != tool_data["owner"]:
        raise ValueError(
            "Owner của final response không khớp tool result."
        )

    trace.append({
        "stage": "final response",
        "data": triage.model_dump()
    })

    return triage, trace

st.set_page_config(
    page_title="Issue Triage",
    layout="wide"
)

st.title("Issue Triage Mini-App")
st.caption("Structured Output · Function Calling · Application Validation")

issue = st.text_area(
    "Mô tả issue",
    value="Nút thanh toán trả HTTP 500 với mọi thẻ Visa từ 14:30.",
    height=150
)

if st.button(
    "Phân loại issue",
    type="primary",
    use_container_width=True
):
    if not issue.strip():
        st.warning("Hãy nhập mô tả issue.")

    else:
        try:
            with st.spinner("Đang phân loại issue..."):
                triage, trace = run_triage(issue.strip())

            st.success("Phân loại và validate thành công.")

            left, right = st.columns(2)

            with left:
                st.subheader("IssueTriage")
                st.json(triage.model_dump())

            with right:
                st.subheader("Workflow Trace")

                for index, item in enumerate(trace, start=1):
                    with st.expander(
                        f"{index}. {item['stage']}",
                        expanded=True
                    ):
                        if isinstance(item["data"], dict):
                            st.json(item["data"])
                        else:
                            st.write(item["data"])

        except Exception as error:
            st.error(f"Không chạy được: {error}")