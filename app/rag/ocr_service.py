from pathlib import Path

from app.config import (
    ENABLE_OCR,
    OCR_DPI,
    OCR_LANGUAGES,
    OCR_MAX_PDF_PAGES,
    TESSERACT_CMD,
)


OCR_ENGINE = "tesseract"


def _missing_dependency_warning(package: str) -> str:
    return f"OCR unavailable: install `{package}` and Tesseract OCR."


def _load_pytesseract():
    try:
        import pytesseract
    except ImportError:
        return None, _missing_dependency_warning("pytesseract")

    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

    return pytesseract, ""


def _load_image_module():
    try:
        from PIL import Image
    except ImportError:
        return None, _missing_dependency_warning("Pillow")

    return Image, ""


def _ocr_image_object(image, page=None) -> dict:
    if not ENABLE_OCR:
        return {
            "text": "",
            "page": page,
            "ocr_used": False,
            "ocr_engine": OCR_ENGINE,
            "warnings": ["OCR is disabled."],
        }

    pytesseract, warning = _load_pytesseract()

    if warning:
        return {
            "text": "",
            "page": page,
            "ocr_used": False,
            "ocr_engine": OCR_ENGINE,
            "warnings": [warning],
        }

    try:
        text = pytesseract.image_to_string(image, lang=OCR_LANGUAGES) or ""
    except Exception as exc:
        return {
            "text": "",
            "page": page,
            "ocr_used": False,
            "ocr_engine": OCR_ENGINE,
            "warnings": [f"OCR failed: {exc}"],
        }

    warnings = []

    if not text.strip():
        warnings.append("OCR completed but no text was found.")

    return {
        "text": text,
        "page": page,
        "ocr_used": True,
        "ocr_engine": OCR_ENGINE,
        "warnings": warnings,
    }


def ocr_image_file(path: Path) -> dict:
    Image, warning = _load_image_module()

    if warning:
        return {
            "text": "",
            "page": None,
            "ocr_used": False,
            "ocr_engine": OCR_ENGINE,
            "warnings": [warning],
        }

    try:
        with Image.open(path) as image:
            return _ocr_image_object(image, page=None)
    except Exception as exc:
        return {
            "text": "",
            "page": None,
            "ocr_used": False,
            "ocr_engine": OCR_ENGINE,
            "warnings": [f"Image OCR failed: {exc}"],
        }


def ocr_pdf_file(path: Path, progress=None) -> list[dict]:
    if not ENABLE_OCR:
        return [
            {
                "text": "",
                "page": None,
                "ocr_used": False,
                "ocr_engine": OCR_ENGINE,
                "warnings": ["OCR is disabled."],
            }
        ]

    try:
        import fitz
    except ImportError:
        return [
            {
                "text": "",
                "page": None,
                "ocr_used": False,
                "ocr_engine": OCR_ENGINE,
                "warnings": [_missing_dependency_warning("PyMuPDF")],
            }
        ]

    pages = []
    zoom = max(72, OCR_DPI) / 72
    matrix = fitz.Matrix(zoom, zoom)

    try:
        with fitz.open(path) as document:
            page_count = min(len(document), OCR_MAX_PDF_PAGES)

            for index in range(page_count):
                page_number = index + 1

                if progress:
                    progress("ocr_page", f"OCR page {page_number}/{page_count}.")

                page = document.load_page(index)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                image_bytes = pixmap.tobytes("png")
                page_result = _ocr_png_bytes(image_bytes, page=page_number)
                pages.append(page_result)

            if len(document) > OCR_MAX_PDF_PAGES:
                pages.append(
                    {
                        "text": "",
                        "page": None,
                        "ocr_used": False,
                        "ocr_engine": OCR_ENGINE,
                        "warnings": [
                            f"OCR stopped after {OCR_MAX_PDF_PAGES} pages to avoid a long import."
                        ],
                    }
                )

    except Exception as exc:
        return [
            {
                "text": "",
                "page": None,
                "ocr_used": False,
                "ocr_engine": OCR_ENGINE,
                "warnings": [f"PDF OCR failed: {exc}"],
            }
        ]

    return pages


def _ocr_png_bytes(image_bytes: bytes, page=None) -> dict:
    Image, warning = _load_image_module()

    if warning:
        return {
            "text": "",
            "page": page,
            "ocr_used": False,
            "ocr_engine": OCR_ENGINE,
            "warnings": [warning],
        }

    try:
        from io import BytesIO

        with Image.open(BytesIO(image_bytes)) as image:
            return _ocr_image_object(image, page=page)
    except Exception as exc:
        return {
            "text": "",
            "page": page,
            "ocr_used": False,
            "ocr_engine": OCR_ENGINE,
            "warnings": [f"OCR image render failed: {exc}"],
        }
