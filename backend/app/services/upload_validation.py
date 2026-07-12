from __future__ import annotations

from typing import BinaryIO, Collection, Optional

from app.core.exceptions import InvalidUploadError


class UploadValidator:
    def __init__(self, allowed_types: Collection[str], max_bytes: int) -> None:
        self.allowed_types = frozenset(allowed_types)
        self.max_bytes = max_bytes

    def validate_metadata(self, content_type: Optional[str]) -> None:
        if content_type not in self.allowed_types:
            raise InvalidUploadError("Tipo de imagem não permitido")

    def validate_size(self, source: BinaryIO) -> None:
        current = source.tell()
        source.seek(0, 2)
        size = source.tell()
        source.seek(current)
        if size <= 0:
            raise InvalidUploadError("A imagem está vazia")
        if size > self.max_bytes:
            raise InvalidUploadError("A imagem excede o limite configurado")
