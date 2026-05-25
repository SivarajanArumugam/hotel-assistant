from langchain.tools import tool
from rag.retriever import retrieve_context


@tool
def search_hotel_knowledge(query: str) -> str:
    """
    Search the hotel's official document to answer questions about hotel
    policies, amenities, food options, hygiene practices, check-in and
    check-out times, dining, facilities, or any general hotel information.
    Always use this tool first before answering any factual question about
    the hotel. Do NOT use this tool for reservation actions.
    """
    context = retrieve_context(query)
    if context.startswith("[RAG unavailable"):
        return (
            "The hotel knowledge base is currently unavailable. "
            "Please contact the front desk for assistance."
        )
    return context
