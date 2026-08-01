import subprocess
from pathlib import Path

from app.services import ocr


def test_ocr_pdf_renders_pages_and_uses_arabic_language(monkeypatch):
    monkeypatch.setattr(ocr.shutil, "which", lambda command: f"/fake/{command}")
    calls: list[list[str]] = []

    def fake_run(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if "--list-langs" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                "List of available languages:\nara\neng\n",
                "",
            )
        if command[0].endswith("pdftoppm"):
            Path(f"{command[-1]}-1.png").write_bytes(b"fake-image")
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.CompletedProcess(
            command,
            0,
            "الحمد لله رب العالمين، أما بعد فاتقوا الله عباد الله واصبروا واشكروا.",
            "",
        )

    monkeypatch.setattr(ocr, "_run", fake_run)

    text = ocr.ocr_pdf(b"%PDF fake scan", page_count=1)

    assert "الحمد لله" in text
    tesseract_call = calls[-1]
    assert "ara" in tesseract_call
    assert "--psm" in tesseract_call
