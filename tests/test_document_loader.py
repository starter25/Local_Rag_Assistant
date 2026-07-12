import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app.rag.document_loader import SUPPORTED_DOCUMENT_EXTENSIONS, load_document


def write_minimal_xlsx(path: Path):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Sales" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <si><t>Product</t></si>
  <si><t>Price</t></si>
  <si><t>Keyboard</t></si>
</sst>""",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="s"><v>0</v></c>
      <c r="B1" t="s"><v>1</v></c>
    </row>
    <row r="2">
      <c r="A2" t="s"><v>2</v></c>
      <c r="B2"><v>30000</v></c>
    </row>
  </sheetData>
</worksheet>""",
        )


class DocumentLoaderTests(unittest.TestCase):
    def test_supported_extensions_include_code_csv_and_xlsx(self):
        self.assertIn(".py", SUPPORTED_DOCUMENT_EXTENSIONS)
        self.assertIn(".csv", SUPPORTED_DOCUMENT_EXTENSIONS)
        self.assertIn(".xlsx", SUPPORTED_DOCUMENT_EXTENSIONS)
        self.assertIn(".png", SUPPORTED_DOCUMENT_EXTENSIONS)
        self.assertIn(".jpg", SUPPORTED_DOCUMENT_EXTENSIONS)

    def test_load_code_file_as_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.py"
            path.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

            pages = load_document(path)

        self.assertEqual(len(pages), 1)
        self.assertIn("Type: code", pages[0]["text"])
        self.assertIn("Language: Python", pages[0]["text"])
        self.assertIn("def hello", pages[0]["text"])

    def test_load_csv_file_as_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sales.csv"
            path.write_text("item,price\nkeyboard,30000\n", encoding="utf-8")

            pages = load_document(path)

        self.assertEqual(len(pages), 1)
        self.assertIn("Format: CSV", pages[0]["text"])
        self.assertIn("Row 1: item=keyboard, price=30000", pages[0]["text"])

    def test_load_xlsx_file_as_sheet_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sales.xlsx"
            write_minimal_xlsx(path)

            pages = load_document(path)

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["page"], "Sales")
        self.assertIn("Type: spreadsheet", pages[0]["text"])
        self.assertIn("Row 1: Product=Keyboard, Price=30000", pages[0]["text"])

    @patch("app.rag.document_loader.ocr_image_file")
    def test_load_image_file_uses_ocr(self, mock_ocr_image):
        mock_ocr_image.return_value = {
            "text": "receipt total 12000",
            "page": None,
            "ocr_used": True,
            "ocr_engine": "tesseract",
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "receipt.png"
            path.write_bytes(b"fake image")

            pages = load_document(path)

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["text"], "receipt total 12000")
        self.assertTrue(pages[0]["ocr_used"])
        self.assertIn("OCR was used", pages[0]["warnings"][0])
        mock_ocr_image.assert_called_once_with(path)

    @patch("app.rag.document_loader.ocr_pdf_file")
    @patch("app.rag.document_loader.PdfReader")
    def test_sparse_pdf_uses_ocr_fallback(self, mock_pdf_reader, mock_ocr_pdf):
        class FakePage:
            def extract_text(self):
                return ""

        class FakeReader:
            pages = [FakePage()]

        mock_pdf_reader.return_value = FakeReader()
        mock_ocr_pdf.return_value = [
            {
                "text": "scanned pdf text",
                "page": 1,
                "ocr_used": True,
                "ocr_engine": "tesseract",
                "warnings": [],
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scan.pdf"
            path.write_bytes(b"%PDF fake")

            pages = load_document(path)

        self.assertEqual(pages[0]["text"], "scanned pdf text")
        self.assertTrue(pages[0]["ocr_used"])
        mock_ocr_pdf.assert_called_once()


if __name__ == "__main__":
    unittest.main()
