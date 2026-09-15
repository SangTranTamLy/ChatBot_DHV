"""Cơ chế chia đoạn (chunking) nhận biết tiêu đề dành cho corpus Markdown DHV."""

from __future__ import annotations

import hashlib
from typing import Iterable

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter


DEFAULT_CHUNK_SIZE = 900
DEFAULT_CHUNK_OVERLAP = 120


def _document_id(document: Document) -> str:
    identity = "|".join(
        [
            str(document.metadata.get("source_url", "")),
            str(document.metadata.get("source_file", "")),
            str(document.metadata.get("title", "")),
        ]
    )
    return hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]


def split_documents(
    documents: Iterable[Document],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Document]:
    """Chia tài liệu theo các tiêu đề, sau đó chia nhỏ các phần tiêu đề dài.

    Mỗi phần tiêu đề được xử lý độc lập để nội dung từ các loại học bổng,
    ngày tháng hoặc thủ tục khác nhau không bị gộp chung vào một đoạn (chunk).
    """

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be between zero and chunk_size - 1")

    heading_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[
            ("#", "heading_1"),
            ("##", "heading_2"),
            ("###", "heading_3"),
        ],
        strip_headers=False,
    )
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks: list[Document] = []
    for document in documents:
        sections = heading_splitter.split_text(document.page_content)
        if not sections:
            sections = [Document(page_content=document.page_content, metadata={})]

        document_id = _document_id(document)
        document_chunk_index = 0
        for section_index, section in enumerate(sections):
            section_metadata = dict(section.metadata)
            heading_values = [
                section_metadata[key]
                for key in ("heading_1", "heading_2", "heading_3")
                if section_metadata.get(key)
            ]
            heading_path = " > ".join(str(value) for value in heading_values)
            section_chunks = text_splitter.split_documents(
                [Document(page_content=section.page_content, metadata={})]
            )

            for section_chunk_index, section_chunk in enumerate(section_chunks):
                content_hash = hashlib.sha1(
                    section_chunk.page_content.encode("utf-8")
                ).hexdigest()[:8]
                metadata = dict(document.metadata)
                metadata.update(section_metadata)
                metadata.update(
                    {
                        "document_id": document_id,
                        "section_index": section_index,
                        "section_chunk_index": section_chunk_index,
                        "chunk_index": document_chunk_index,
                        "heading_path": heading_path,
                        "chunk_id": (
                            f"{document_id}-{section_index:03d}-"
                            f"{section_chunk_index:03d}-{content_hash}"
                        ),
                        "chunk_char_count": len(section_chunk.page_content),
                    }
                )
                chunks.append(
                    Document(page_content=section_chunk.page_content, metadata=metadata)
                )
                document_chunk_index += 1

    return chunks


__all__ = [
    "DEFAULT_CHUNK_OVERLAP",
    "DEFAULT_CHUNK_SIZE",
    "split_documents",
]
