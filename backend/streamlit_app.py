from __future__ import annotations

from uuid import uuid4

import httpx
import streamlit as st


DEFAULT_API_URL = "http://localhost:9000/api/v1/chat"
DEFAULT_CONFIG_API_URL = "http://localhost:9000/api/v1/config/ai"


def _init_state() -> None:
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("conversation_id", None)
    st.session_state.setdefault("session_id", str(uuid4()))


def _send_message(
    *,
    api_url: str,
    app_id: str,
    service_key: str,
    authorization: str,
    message: str,
) -> dict:
    headers = {
        "X-Master-Chatbot-Service-Key": service_key,
        "X-Request-Id": str(uuid4()),
    }
    if authorization.strip():
        headers["Authorization"] = authorization.strip()

    payload = {
        "app_id": app_id,
        "message": message,
        "conversation_id": st.session_state.get("conversation_id"),
        "session_id": st.session_state["session_id"],
        "request_id": str(uuid4()),
    }

    with httpx.Client(timeout=60.0) as client:
        response = client.post(api_url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()


def _load_ai_config(*, config_api_url: str, config_key: str) -> dict:
    with httpx.Client(timeout=20.0) as client:
        response = client.get(config_api_url, headers={"X-Master-Chatbot-Config-Key": config_key})
        response.raise_for_status()
        return response.json()


def _update_ai_config(*, config_api_url: str, config_key: str, provider: str, api_key: str, model: str) -> dict:
    payload = {"ai_provider": provider, "groq_api_key": api_key, "groq_model": model}
    with httpx.Client(timeout=20.0) as client:
        response = client.put(config_api_url, json=payload, headers={"X-Master-Chatbot-Config-Key": config_key})
        response.raise_for_status()
        return response.json()


def main() -> None:
    st.set_page_config(page_title="Master Chatbot", page_icon="💬", layout="centered")
    _init_state()

    st.title("Master Chatbot")
    st.caption("Streamlit UI for the Python Master Chatbot backend")

    with st.sidebar:
        st.header("Connection")
        api_url = st.text_input("Chat API URL", value=DEFAULT_API_URL)
        config_api_url = st.text_input("AI Config API URL", value=DEFAULT_CONFIG_API_URL)
        app_id = st.text_input("App ID", value="ecommerce")
        service_key = st.text_input("Service key", type="password")
        config_key = st.text_input("Config key", type="password")
        authorization = st.text_input("Authorization header", placeholder="Bearer <user-jwt>", type="password")

        st.header("AI Provider Configuration")
        if st.button("Load current configuration", use_container_width=True, disabled=not config_key.strip()):
            try:
                st.session_state["ai_config"] = _load_ai_config(config_api_url=config_api_url, config_key=config_key.strip())
            except httpx.HTTPError as exc:
                st.error(f"Could not load AI configuration: {exc}")

        current_config = st.session_state.get("ai_config", {})
        provider = st.selectbox("AI Provider", ["groq"], index=0)
        masked_key = str(current_config.get("groq_api_key_masked") or "")
        api_key = st.text_input("Groq API Key", value="", placeholder=masked_key or "gsk_...", type="password")
        model = st.text_input("Groq Model", value=str(current_config.get("groq_model") or ""))
        if st.button("Update Configuration", use_container_width=True, disabled=not config_key.strip()):
            if not api_key.strip():
                st.error("Enter the full Groq API key to update it.")
            else:
                try:
                    st.session_state["ai_config"] = _update_ai_config(
                        config_api_url=config_api_url,
                        config_key=config_key.strip(),
                        provider=provider,
                        api_key=api_key,
                        model=model,
                    )
                    st.success("AI configuration updated.")
                except httpx.HTTPStatusError as exc:
                    st.error(f"Configuration update failed with HTTP {exc.response.status_code}: {exc.response.text}")
                except httpx.HTTPError as exc:
                    st.error(f"Could not update AI configuration: {exc}")

        if st.button("New conversation", use_container_width=True):
            st.session_state["messages"] = []
            st.session_state["conversation_id"] = None
            st.session_state["session_id"] = str(uuid4())
            st.rerun()

    for item in st.session_state["messages"]:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])
            if item.get("data"):
                with st.expander("Data"):
                    st.json(item["data"])

    prompt = st.chat_input("Type your message")
    if not prompt:
        return

    st.session_state["messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    if not service_key.strip():
        error = "Service key is required in the sidebar."
        st.session_state["messages"].append({"role": "assistant", "content": error})
        with st.chat_message("assistant"):
            st.error(error)
        return

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                result = _send_message(
                    api_url=api_url,
                    app_id=app_id,
                    service_key=service_key,
                    authorization=authorization,
                    message=prompt,
                )
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text
                content = f"Request failed with HTTP {exc.response.status_code}: {detail}"
                st.error(content)
                st.session_state["messages"].append({"role": "assistant", "content": content})
                return
            except httpx.HTTPError as exc:
                content = f"Could not reach Master Chatbot: {exc}"
                st.error(content)
                st.session_state["messages"].append({"role": "assistant", "content": content})
                return

        content = str(result.get("message") or "No response message returned.")
        st.markdown(content)
        data = result.get("data") or []
        if data:
            with st.expander("Data"):
                st.json(data)

    st.session_state["conversation_id"] = result.get("conversation_id")
    st.session_state["session_id"] = result.get("session_id") or st.session_state["session_id"]
    st.session_state["messages"].append({"role": "assistant", "content": content, "data": data})


if __name__ == "__main__":
    main()
