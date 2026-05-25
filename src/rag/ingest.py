import glob as glob_module
import json
import logging
import os
import re
from typing import Optional

import chromadb
import pymupdf4llm
from groq import Groq
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

from core.config import settings

logger = logging.getLogger(__name__)


def find_pdf_in_data_folder() -> Optional[str]:
    """
    Searches settings.data_folder for *.pdf files.
    Returns the path of the first PDF found (sorted alphabetically).
    Returns None if no PDF is found.
    Logs which PDF was selected if more than one is found.
    """
    pattern = os.path.join(settings.data_folder, "*.pdf")
    pdfs = sorted(glob_module.glob(pattern))
    if not pdfs:
        return None
    if len(pdfs) > 1:
        logger.info("Multiple PDFs found in data folder; using: %s", pdfs[0])
    return pdfs[0]


def ingest_pdf(pdf_path: str) -> int:
    """Ingests a PDF into ChromaDB. Returns total number of chunks stored."""
    markdown_text = pymupdf4llm.to_markdown(pdf_path)

    # Strip markdown formatting so BM25 tokenization matches plain query tokens
    plain_text = re.sub(r'[*_]{1,3}', '', markdown_text)
    plain_text = re.sub(r'^#{1,6}\s*', '', plain_text, flags=re.MULTILINE)
    plain_text = re.sub(r'\n{3,}', '\n\n', plain_text)

    splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=50)
    chunks = splitter.split_text(plain_text)

    model = SentenceTransformer(settings.embedding_model)
    embeddings = model.encode(chunks).tolist()

    client = chromadb.PersistentClient(path=settings.chroma_db_path)
    try:
        client.delete_collection(settings.collection_name)
    except Exception:
        pass
    collection = client.get_or_create_collection(
        name=settings.collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    ids = [f"chunk_{i}" for i in range(len(chunks))]
    collection.add(documents=chunks, embeddings=embeddings, ids=ids)

    first_three = "\n\n".join(chunks[:3])
    groq_client = Groq(api_key=settings.groq_api_key)
    completion = groq_client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Based on the following text excerpts, write a 2–3 sentence description "
                    f"of what this document covers:\n\n{first_three}"
                ),
            }
        ],
        temperature=0,
    )
    domain_description = completion.choices[0].message.content.strip()

    meta_path = os.path.join(settings.chroma_db_path, "doc_meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(
            {"domain_description": domain_description, "chunk_count": len(chunks), "source": pdf_path},
            f,
            indent=2,
        )

    logger.info("Ingested %d chunks from %s", len(chunks), pdf_path)
    return len(chunks)
