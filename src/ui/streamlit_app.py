import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import re
import uuid
import chromadb
import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def _redact_emails_from_history(messages: list) -> None:
    """Replace email addresses in stored chat history with [email on file]."""
    for msg in messages:
        msg["content"] = _EMAIL_RE.sub("[email on file]", msg["content"])

from core.config import settings
from core.guardrails import check_injection, is_off_topic
from core.logging_config import setup_logging

# Auto-generate and persist FERNET_KEY if missing
if not settings.fernet_key:
    from cryptography.fernet import Fernet
    _key = Fernet.generate_key().decode()
    _env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    with open(_env_path, "a") as _f:
        _f.write(f"\nFERNET_KEY={_key}\n")
    settings.fernet_key = _key
from rag.ingest import find_pdf_in_data_folder, ingest_pdf
from agent.react_agent import get_agent_executor
from db.operations import purge_old_bookings

setup_logging()

st.set_page_config(
    page_title="Hotel Concierge",
    page_icon="🏨",
    layout="centered",
    initial_sidebar_state="expanded",
)


def init_session_state() -> None:
    """Called on first load and after 'New conversation' is clicked."""
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.messages = []
    st.session_state.draft = {}


def ensure_knowledge_base_ready() -> bool:
    """
    Checks whether ChromaDB already contains documents for the hotel.
    If not, finds the PDF in the data folder and ingests it.
    Returns True if the knowledge base is ready.
    Calls st.error() and st.stop() if no PDF is found.
    """
    try:
        client = chromadb.PersistentClient(path=settings.chroma_db_path)
        col = client.get_collection(settings.collection_name)
        if col.count() > 0:
            return True
    except Exception:
        pass

    pdf_path = find_pdf_in_data_folder()

    if pdf_path is None:
        st.error(
            "No PDF file found in the data/ folder. "
            "Please place your hotel document (PDF) in the data/ folder and restart the app."
        )
        st.stop()

    with st.spinner(f"Building knowledge base from {os.path.basename(pdf_path)}..."):
        ingest_pdf(pdf_path)
    st.success("Knowledge base ready.")
    return True


if "session_id" not in st.session_state:
    init_session_state()

if "purge_done" not in st.session_state:
    purge_old_bookings(days=365)
    st.session_state.purge_done = True

ensure_knowledge_base_ready()

with st.sidebar:
    st.title("Hotel Concierge")
    st.divider()
    if st.button("New conversation", type="primary"):
        init_session_state()
        st.rerun()
    st.divider()
    st.markdown("**What I can help with:**")
    st.markdown(
        "- Hotel information & policies\n"
        "- Food and dining options\n"
        "- Making a reservation\n"
        "- Viewing a reservation\n"
        "- Cancelling a reservation"
    )

st.title("Hotel Concierge")
st.caption("Ask me anything about the hotel, or manage your reservation.")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

user_input = st.chat_input("Ask me anything about the hotel…")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    is_inject, refusal = check_injection(user_input)
    if is_inject:
        st.session_state.messages.append({"role": "assistant", "content": refusal})
        with st.chat_message("assistant"):
            st.write(refusal)
        st.stop()

    recent_msgs = st.session_state.messages[-3:-1]
    recent_context = " ".join(m["content"] for m in recent_msgs)
    is_ot, refusal = is_off_topic(user_input, recent_context=recent_context)
    if is_ot:
        st.session_state.messages.append({"role": "assistant", "content": refusal})
        with st.chat_message("assistant"):
            st.write(refusal)
        st.stop()

    history = []
    for msg in st.session_state.messages[:-1]:
        if msg["role"] == "user":
            history.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            history.append(AIMessage(content=msg["content"]))

    with st.spinner("Thinking…"):
        executor = get_agent_executor(
            session_id=st.session_state.session_id,
            chat_history=history,
        )
        result = executor.invoke({"input": user_input, "chat_history": history})
        response = result["output"]

    st.session_state.messages.append({"role": "assistant", "content": response})
    if "Reservation confirmed" in response:
        _redact_emails_from_history(st.session_state.messages)
    with st.chat_message("assistant"):
        st.write(response)
