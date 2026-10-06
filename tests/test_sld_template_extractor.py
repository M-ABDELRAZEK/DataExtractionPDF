import tempfile
import unittest
from pathlib import Path

from core.sld_template_extractor import (
    IndexedPage,
    PDFIndex,
    SLDTemplateExtractor,
    TemplateRow,
    normalize_text,
    tokenise,
)


def make_page(number, text, kind="MAIN_SOW", priority=0):
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    return IndexedPage(
        page_number=number,
        text=text,
        normalized=normalize_text(text),
        lines=lines,
        line_norms=[normalize_text(x) for x in lines],
        line_tokens=[tokenise(x) for x in lines],
        tokens=tokenise(text),
        source_kind=kind,
        source_priority=priority,
    )


class ExtractorTests(unittest.TestCase):
    def test_main_sow_wins_conflict(self):
        pages = [
            make_page(10, "13.8 kV SWITCHGEAR\nRated Short Circuit 25 kA for 3 sec", "MAIN_SOW", 0),
            make_page(200, "13.8 kV SWITCHGEAR\nRated Short Circuit 25 kA for 1 sec", "PROJECT_APPENDIX", 1),
        ]
        ext = SLDTemplateExtractor(PDFIndex(pages), "x.pdf")
        row = TemplateRow(3, "SWGR", "Rating", "Short Circuit", "SWGR", "Rating")
        result = ext.extract_row(row)
        self.assertIn("25 kA", result.value)
        self.assertIn("3", result.value)
        self.assertEqual(result.pages, "10")

    def test_same_value_keeps_multiple_physical_pages(self):
        pages = [
            make_page(10, "NGR Neutral Grounding Resistor 5.3 ohms"),
            make_page(12, "NGR Neutral Grounding Resistor 5.3 ohms"),
        ]
        ext = SLDTemplateExtractor(PDFIndex(pages), "x.pdf")
        row = TemplateRow(3, "NGR", "Rating", "Resistance", "NGR", "Rating")
        result = ext.extract_row(row)
        self.assertEqual(result.pages, "10; 12")

    def test_missing_is_na(self):
        ext = SLDTemplateExtractor(PDFIndex([make_page(1, "unrelated")]), "x.pdf")
        row = TemplateRow(3, "GIS", "CB", "Rating", "GIS", "CB")
        result = ext.extract_row(row)
        self.assertEqual((result.value, result.pages, result.reference), ("NA", "NA", "NA"))

    def test_project_name_falls_back_to_pdf_filename(self):
        ext = SLDTemplateExtractor(PDFIndex([make_page(1, "no title here")]), "/tmp/My Project PTS.pdf")
        self.assertEqual(ext.extract_project_name(), "My Project PTS")

    def test_physical_page_number_is_preserved(self):
        page = make_page(777, "NGR Neutral Grounding Resistor 5.3 ohms")
        ext = SLDTemplateExtractor(PDFIndex([page]), "x.pdf")
        row = TemplateRow(3, "NGR", "Rating", "Resistance", "NGR", "Rating")
        self.assertEqual(ext.extract_row(row).pages, "777")


if __name__ == "__main__":
    unittest.main()
