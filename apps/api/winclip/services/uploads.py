"""Parser multipart en streaming para `POST /api/projects`.

`python-multipart` procesa el cuerpo chunk a chunk: cada parte de archivo se escribe
directamente en `storage/projects/<id>/source/` sin pasar por memoria ni por `/tmp`
(design, decisión 5). Un fallo a mitad deja constancia del archivo parcial para que el
router limpie la carpeta del proyecto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from fastapi import Request
from python_multipart.multipart import MultipartParser, parse_options_header

ALLOWED_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".webm"})
CHUNK_SIZE = 1024 * 1024


class UploadError(ValueError):
    """Cuerpo multipart inválido; lleva el código HTTP sugerido."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class UploadTooLargeError(UploadError):
    """El cuerpo supera `UPLOAD_MAX_BYTES`."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=413)


@dataclass
class MultipartUpload:
    """Campos de texto y archivo escrito en disco."""

    fields: dict[str, str] = field(default_factory=dict)
    file_path: Path | None = None
    filename: str | None = None
    bytes_written: int = 0


def _decode(value: bytes) -> str:
    return value.decode("utf-8", "replace").strip()


def _boundary(content_type: str | None) -> bytes:
    if not content_type or not content_type.lower().startswith("multipart/form-data"):
        raise UploadError("se esperaba multipart/form-data")
    _, options = parse_options_header(content_type)
    boundary = options.get(b"boundary")
    if not boundary:
        raise UploadError("falta el boundary del formulario multipart")
    return boundary


async def stream_multipart(
    request: Request,
    *,
    directory: Path,
    max_bytes: int,
) -> MultipartUpload:
    """Parsea el formulario y escribe el archivo directamente en `directory`."""
    directory.mkdir(parents=True, exist_ok=True)
    result = MultipartUpload()

    state: dict[str, object] = {
        "header_field": b"",
        "header_value": b"",
        "headers": [],
        "field": "",
        "filename": "",
        "handle": None,
        "text": bytearray(),
        "total": 0,
    }

    def part_begin() -> None:
        state.update(
            header_field=b"",
            header_value=b"",
            headers=[],
            field="",
            filename="",
            text=bytearray(),
        )

    def header_field(data: bytes, start: int, end: int) -> None:
        current = state["header_field"]
        value = state["header_value"]
        if isinstance(current, bytes) and isinstance(value, bytes) and current:
            state["headers"].append((current, value))  # type: ignore[union-attr]
        state["header_field"] = data[start:end]
        state["header_value"] = b""

    def header_value(data: bytes, start: int, end: int) -> None:
        state["header_value"] = state["header_value"] + data[start:end]  # type: ignore[operator]

    def headers_finished() -> None:
        headers = state["headers"]
        assert isinstance(headers, list)
        field = state["header_field"]
        value = state["header_value"]
        if isinstance(field, bytes) and isinstance(value, bytes) and field:
            headers.append((field, value))
        disposition = next(
            (value for name, value in headers if name.lower() == b"content-disposition"),
            b"",
        )
        _, options = parse_options_header(disposition)
        state["field"] = _decode(options.get(b"name", b""))
        filename = _decode(options.get(b"filename", b""))
        state["filename"] = filename
        if not filename:
            return

        extension = Path(filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
            raise UploadError(
                f"extensión no permitida ({extension or 'sin extensión'}); usa {allowed}"
            )
        target = directory / f"original{extension}"
        state["handle"] = target.open("wb")
        result.file_path = target
        result.filename = filename

    def part_data(data: bytes, start: int, end: int) -> None:
        chunk = data[start:end]
        total = int(state["total"]) + len(chunk)  # type: ignore[arg-type]
        if total > max_bytes:
            raise UploadTooLargeError(f"el archivo supera el límite de {max_bytes} bytes")
        state["total"] = total
        handle = state["handle"]
        if handle is None:
            buffer = state["text"]
            assert isinstance(buffer, bytearray)
            buffer.extend(chunk)
        else:
            handle.write(chunk)  # type: ignore[union-attr]
            result.bytes_written += len(chunk)

    def part_end() -> None:
        handle = state["handle"]
        if handle is not None:
            handle.close()  # type: ignore[union-attr]
            state["handle"] = None
            return
        buffer = state["text"]
        assert isinstance(buffer, bytearray)
        result.fields[str(state["field"])] = buffer.decode("utf-8", "replace").strip()

    parser = MultipartParser(
        _boundary(request.headers.get("content-type")),
        {
            "on_part_begin": part_begin,
            "on_header_field": header_field,
            "on_header_value": header_value,
            "on_headers_finished": headers_finished,
            "on_part_data": part_data,
            "on_part_end": part_end,
        },
    )

    try:
        async for chunk in request.stream():
            if not chunk:
                continue
            total = int(state["total"]) + len(chunk)  # type: ignore[arg-type]
            if total > max_bytes + CHUNK_SIZE:
                raise UploadTooLargeError(f"el archivo supera el límite de {max_bytes} bytes")
            parser.write(chunk)
    except Exception:
        handle = state["handle"]
        if handle is not None:
            handle.close()  # type: ignore[union-attr]
        raise
    finally:
        parser.finalize()

    if result.filename and result.bytes_written == 0:
        raise UploadError("el archivo subido está vacío")
    return result
