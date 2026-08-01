"""Backward-compatible PDF helpers.

New upload code should use :mod:`app.services.documents`, which supports PDF and DOCX.
"""

from fastapi import HTTPException, UploadFile, status

from app.services.documents import (
    DocumentKind,
    UploadedDocument,
    extract_document_text,
    read_document_upload,
    store_document,
)


async def read_pdf_upload(upload: UploadFile) -> bytes:
    document = await read_document_upload(upload)
    if document.kind != DocumentKind.PDF:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PDF files are accepted")
    return document.content


def extract_pdf_text(content: bytes, require_arabic: bool = False) -> str:
    return extract_document_text(
        UploadedDocument(content=content, kind=DocumentKind.PDF),
        require_arabic=require_arabic,
    )


def store_pdf(content: bytes, category: str) -> tuple[str, str]:
    return store_document(
        UploadedDocument(content=content, kind=DocumentKind.PDF),
        category,
    )
