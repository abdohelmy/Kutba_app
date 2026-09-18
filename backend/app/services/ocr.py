import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.config import get_settings


class OcrUnavailableError(ValueError):
    pass


class OcrProcessingError(ValueError):
    pass


def _command_path(command: str, label: str) -> str:
    path = shutil.which(command)
    if path is None:
        raise OcrUnavailableError(
            f"Scanned PDF detected, but {label} is not installed on the API server"
        )
    return path


def _run(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.setdefault("OMP_THREAD_LIMIT", "2")
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=environment,
        )
    except subprocess.TimeoutExpired as exc:
        raise OcrProcessingError("Arabic OCR timed out while processing the scanned PDF") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "OCR command failed").strip()
        raise OcrProcessingError(f"Arabic OCR failed: {detail[:500]}") from exc


def ocr_pdf(content: bytes, page_count: int) -> str:
    settings = get_settings()
    if not settings.ocr_enabled:
        raise OcrUnavailableError("Scanned PDF detected, but OCR is disabled on the API server")
    if page_count > settings.max_ocr_pages:
        raise OcrProcessingError(
            f"The scanned PDF has {page_count} pages; the OCR limit is {settings.max_ocr_pages}"
        )

    renderer = _command_path(settings.pdftoppm_command, "Poppler/pdftoppm")
    tesseract = _command_path(settings.tesseract_command, "Tesseract OCR with Arabic data")
    languages = _run([tesseract, "--list-langs"], timeout=15).stdout.splitlines()
    requested_languages = settings.ocr_languages.split("+")
    missing = [language for language in requested_languages if language not in languages]
    if missing:
        raise OcrUnavailableError(
            "Scanned PDF detected, but Tesseract language data is missing: " + ", ".join(missing)
        )

    with TemporaryDirectory(prefix="khutba-ocr-") as temporary_directory:
        directory = Path(temporary_directory)
        input_path = directory / "input.pdf"
        page_prefix = directory / "page"
        input_path.write_bytes(content)
        _run(
            [
                renderer,
                "-png",
                "-gray",
                "-r",
                str(settings.ocr_dpi),
                "-f",
                "1",
                "-l",
                str(page_count),
                str(input_path),
                str(page_prefix),
            ],
            timeout=settings.ocr_timeout_seconds,
        )
        images = sorted(directory.glob("page-*.png"))
        if len(images) != page_count:
            raise OcrProcessingError("The scanned PDF could not be rendered into all of its pages")

        pages: list[str] = []
        for image in images:
            result = _run(
                [
                    tesseract,
                    str(image),
                    "stdout",
                    "-l",
                    settings.ocr_languages,
                    "--psm",
                    str(settings.ocr_page_segmentation_mode),
                    "-c",
                    "preserve_interword_spaces=1",
                ],
                timeout=settings.ocr_timeout_seconds,
            )
            page_text = result.stdout.strip()
            if page_text:
                pages.append(page_text)
        return "\n\n".join(pages).strip()
