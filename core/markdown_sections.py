"""PDF -> auditable, section-oriented Markdown; no LLM required.

The section title recognizer is intentionally generic: numbered headings, SECTION,
APPENDIX, and known specification document identifiers. The manifest preserves
physical PDF page numbers; no assumption is made about printed page numbers.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import json
import re

from core.pdf_processor import PDFProcessor

SECTION_RE = re.compile(r'^\s*(SECTION\s+(?:[IVXLCDM]+|\d+)\s*[-–—:]\s*\S.{0,120})\s*$', re.I)

# Re-export from pipeline_v2 for backwards compatibility with pipeline_v3
def read_markdown_page_segments(manifest: dict, base_dir: Path) -> dict[int, str]:
    """Rehydrate individual page segments from saved, auditable Markdown files."""
    mapping: dict[int, list[str]] = {}
    splitter = re.compile(r'<!-- PDF_PAGE: (\d+) -->')
    for section in manifest['sections']:
        file = base_dir / section['file']
        chunks = splitter.split(file.read_text(encoding='utf-8'))
        for index in range(1, len(chunks), 2):
            page = int(chunks[index])
            mapping.setdefault(page, []).append(chunks[index + 1])
    return {page: '\n'.join(sections) for page, sections in mapping.items()}
APPENDIX_RE = re.compile(r'^\s*(APPENDIX\s*[-#:]?\s*(?:[IVXLCDM]+|\d+|[A-Z])\b(?:\s*[-–—:]\s*\S.{0,100})?)\s*$', re.I)
NUMBERED_RE = re.compile(r'^\s*((?:[1-9]\d?\.\d{2}(?:\.\d+){0,2}|[1-9]\d?\.\d+\.\d+)\s+[A-Z][^\n]{2,100})\s*$', re.I)
DOC_CODE_RE = re.compile(r'\b(\d{2}-(?:TMSS|SDMS)-\d{2})\b', re.I)
TOC_DOTS = re.compile(r'\.{4,}')


@dataclass
class SectionRecord:
    id: str
    title: str
    file: str
    first_page: int
    last_page: int
    page_numbers: list[int]
    characters: int
    heading_kind: str


def detect_heading(text: str, index: int = 0) -> tuple[str, str] | None:
    value = text.strip()
    if not value or len(value) > 145 or TOC_DOTS.search(value) or re.search(r'\bPAGE\s+\d+\b', value, re.I):
        return None
    if m := SECTION_RE.match(value):
        return ('section', m.group(1))
    if m := APPENDIX_RE.match(value):
        return ('appendix', m.group(1))
    if re.match(r'^\s*\d+\.\d+[A-Z]?\s+(?:Each|Lot|Set|Nos?\.?)(?:\s|$)', value, re.I):
        return None
    if m := NUMBERED_RE.match(value):
        # Most numbered subclauses in PDFs are part of the running text. Treat
        # them as headers only when they appear alone on a reasonably short line.
        if len(m.group(1)) <= 96 and not m.group(1).rstrip().endswith('.'):
            return ('clause', m.group(1))
    return None


def slug(title: str) -> str:
    text = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    return text[:65] or 'untitled'


class MarkdownSectionizer:
    def __init__(self, max_chars: int = 38_000, max_pages: int = 10):
        if max_chars < 100 or max_pages < 1:
            raise ValueError('Invalid Markdown chunk limits')
        self.max_chars = max_chars
        self.max_pages = max_pages

    def convert(self, pdf_path: str | Path, output_dir: str | Path,
                start_page: int = 1, end_page: int | None = None,
                progress=None, stop=None, ocr_missing: bool = False) -> dict:
        pdf_path, output_dir = Path(pdf_path), Path(output_dir)
        sections_dir = output_dir / 'sections'
        sections_dir.mkdir(parents=True, exist_ok=True)
        processor = PDFProcessor(str(pdf_path))
        final_page = min(end_page or processor.total_pages, processor.total_pages)
        if not 1 <= start_page <= final_page:
            raise ValueError('Invalid PDF page range')
        records: list[SectionRecord] = []
        page_meta: list[dict] = []
        title, kind = 'Document introduction', 'intro'
        parts: list[str] = []
        pages: list[int] = []
        chars = 0
        seq = 0
        active_toc = False
        last_doc_code = ''

        def flush():
            nonlocal seq, parts, pages, chars
            if not parts:
                return
            seq += 1
            identifier = f'{seq:04d}_{slug(title)}'
            outfile = sections_dir / f'{identifier}.md'
            body = f'# {title}\n\n' + ''.join(parts)
            outfile.write_text(body, encoding='utf-8')
            records.append(SectionRecord(identifier, title,
                str(outfile.relative_to(output_dir)).replace('\\', '/'),
                pages[0], pages[-1], pages.copy(), chars, kind))
            parts = []
            pages = []
            chars = 0

        def append(page: int, content: str):
            nonlocal chars
            if not content.strip():
                return
            if not pages or pages[-1] != page:
                parts.append(f'\n\n<!-- PDF_PAGE: {page} -->\n\n## Physical PDF page {page}\n\n')
                pages.append(page)
            # Keep extracted table/alignment newlines; literal source may contain
            # Markdown punctuation, so we don't try to interpret it as markup.
            parts.append(content.rstrip() + '\n')
            chars += len(content)

        for index, (page, raw_text, _unused) in enumerate(
            processor.extract_text_pages(start_page - 1, final_page, ocr_empty_pages=ocr_missing), start=1
        ):
            if stop is not None and stop():
                raise InterruptedError('Stopped by user')
            raw_lines = raw_text.splitlines()
            # Identify table-of-contents pages, where heading-looking rows
            # should not be interpreted as real section starts.
            toc_page = (any('TABLE OF CONTENTS' in line.upper() for line in raw_lines[:24])
                        or sum(bool(TOC_DOTS.search(line)) for line in raw_lines[:55]) >= 4)
            # Standards repeat their ID in the page header; switch only when
            # the ID actually changes, not on every page.
            header = '\n'.join(raw_lines[:7])
            m_code = DOC_CODE_RE.search(header)
            if m_code and m_code.group(1).upper() != last_doc_code:
                flush()
                last_doc_code = m_code.group(1).upper()
                title, kind = f'Specification {last_doc_code}', 'standard'

            page_meta.append({'page': page, 'characters': len(raw_text),
                              'empty': not bool(raw_text.strip()),
                              'oversize': len(raw_text) > self.max_chars})
            if not raw_text.strip():
                append(page, '[NO EXTRACTABLE TEXT — IMAGE/OCR REVIEW REQUIRED]')
            else:
                buffer: list[str] = []
                for i, line in enumerate(raw_lines):
                    new_head = None if toc_page else detect_heading(line, i)
                    if new_head and new_head[1].casefold() != title.casefold():
                        if buffer:
                            text = '\n'.join(buffer) + '\n'
                            if chars and (chars + len(text) > self.max_chars or len(pages) >= self.max_pages):
                                flush()
                            append(page, text)
                            buffer = []
                        flush()
                        kind, title = new_head
                    buffer.append(line)
                    if sum(len(x) for x in buffer) > self.max_chars:
                        text = '\n'.join(buffer) + '\n'
                        if chars:
                            flush()
                        append(page, text)
                        buffer = []
                if buffer:
                    text = '\n'.join(buffer) + '\n'
                    if chars and (chars + len(text) > self.max_chars or
                                  (pages and page not in pages and len(pages) >= self.max_pages)):
                        flush()
                    append(page, text)
            if len(pages) >= self.max_pages or chars >= self.max_chars:
                flush()
            if progress:
                progress(index, final_page - start_page + 1)
        flush()
        manifest = {'schema_version': 1, 'pdf_file': pdf_path.name,
                    'pdf_sha256': self._hash_file(pdf_path),
                    'physical_pages_total': processor.total_pages,
                    'ocr_missing_enabled':ocr_missing,
                    'range': [start_page, final_page],
                    'sections': [asdict(x) for x in records], 'pages': page_meta,
                    'empty_pages': sum(p['empty'] for p in page_meta),
                    'oversized_text_pages': [p['page'] for p in page_meta if p['oversize']]}
        (output_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
        return manifest

    @staticmethod
    def _hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with path.open('rb') as handle:
            for block in iter(lambda: handle.read(4 * 1024 * 1024), b''):
                h.update(block)
        return h.hexdigest()
