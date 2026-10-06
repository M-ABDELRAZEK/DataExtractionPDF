"""Template-driven SLD data extraction.

The extractor indexes the uploaded PDF once, then resolves every fixed template
row (Section / Component / Parameter) against the in-memory page index.

Design goals:
- Physical PDF page numbers only (1..N), independent of printed page labels.
- Main SOW wins when conflicting values are found.
- If the winning value occurs on several relevant pages, all page numbers are kept.
- Missing values are returned as ``NA``.
- Notes are intentionally not generated; they remain for manual editing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional
import logging
import re

from openpyxl import load_workbook

from core.pdf_processor import PDFProcessor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class TemplateRow:
    excel_row: int
    section_display: str
    component_display: str
    parameter: str
    section: str
    component: str


@dataclass
class IndexedPage:
    page_number: int
    text: str
    normalized: str
    lines: list[str]
    line_norms: list[str]
    line_tokens: list[set[str]]
    tokens: set[str]
    source_kind: str = "OTHER"
    source_priority: int = 4


@dataclass
class ExtractionCandidate:
    value: str
    page_number: int
    reference: str
    source_priority: int
    score: float


@dataclass
class ExtractionResult:
    value: str = "NA"
    pages: str = "NA"
    reference: str = "NA"


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

GENERIC_PARAMETERS = {
    "NO.", "NO", "RATING", "TYPE", "CLASS", "MAIN", "FUTURE", "SPARE",
    "VOLTAGE", "POWER", "FREQUENCY", "COOLING", "IMPEDANCE", "OLTC",
    "AMBIENT TEMPERATURE", "RESISTANCE", "CURRENT / TIME", "SYSTEM",
}

STOP_WORDS = {
    "THE", "OF", "AND", "OR", "IN", "TO", "FOR", "WITH", "A", "AN",
    "NO", "RATING", "SYSTEM", "MAIN", "FEEDER", "BAY", "BAYS", "CORE",
    "BEFORE", "AFTER", "LOWER", "UPPER", "PHASE", "THREE", "TYPE",
}

ALIASES = {
    "GIS": ["GIS", "GAS INSULATED SWITCHGEAR", "SF6 GAS INSULATED SWITCHGEAR"],
    "SWGR": ["SWITCHGEAR", "13.8 KV SWITCHGEAR", "METAL ENCLOSED SWITCHGEAR"],
    "POWER TRANSFORMER": ["POWER TRANSFORMER", "TRANSFORMER"],
    "AUX TRANSFORMER": ["STATION SERVICE TRANSFORMER", "AUXILIARY TRANSFORMER", "AUX TRANSFORMER"],
    "NGR": ["NGR", "NEUTRAL GROUNDING RESISTOR", "NEUTRAL EARTHING RESISTOR"],
    "STATCOM": ["STATCOM", "STATIC SYNCHRONOUS COMPENSATOR"],
    "OHL FEEDER": ["OHL FEEDER", "OVERHEAD LINE FEEDER", "OVERHEAD FEEDER"],
    "CABLE FEEDER": ["CABLE FEEDER", "UNDERGROUND CABLE FEEDER", "UGC FEEDER", "U/G FEEDER"],
    "BUS COUPLER": ["BUS COUPLER", "BUS TIE"],
    "BUS SECTION": ["BUS SECTION", "BUS-SECTION"],
    "EARTH SW": ["EARTHING SWITCH", "GROUNDING SWITCH", "EARTH SWITCH", "ES"],
    "HS EARTH SW": ["HIGH SPEED EARTHING SWITCH", "HIGH-SPEED EARTHING SWITCH", "HSES"],
    "CB": ["CIRCUIT BREAKER", "CB"],
    "VT": ["VOLTAGE TRANSFORMER", "POTENTIAL TRANSFORMER", "VT", "PT"],
    "CT": ["CURRENT TRANSFORMER", "CT"],
    "SA": ["SURGE ARRESTER", "SURGE ARRESTERS", "ARRESTER"],
    "GIB": ["GIB", "GAS INSULATED BUS", "GIS BUS DUCT", "BUS DUCT"],
    "SIS BUSBAR": ["SOLID INSULATION SYSTEM", "INSULATED CONDENSER BUS", "SIS", "BUS BAR"],
}


VALUE_PATTERNS = {
    "ct": re.compile(
        r"(?P<ratio>\(?\d{2,4}(?:\s*[-/]\s*\d{2,4}){0,4}\)?\s*(?:/|:)\s*1\s*A)"
        r"(?P<rest>.{0,150}?(?:(?:CLASS\b)|(?:CL\.)|(?:PX\b)|(?:5P\d+\b)|(?:10P\d+\b)).{0,120})?",
        re.IGNORECASE,
    ),
    "vt": re.compile(
        r"(?P<value>\d{1,3}(?:\.\d+)?\s*/\s*√?3\s*(?:kV|KV)?.{0,100}?"
        r"\d{2,3}\s*/\s*√?3\s*(?:V|VOLTS?).{0,160})",
        re.IGNORECASE,
    ),
    "voltage": re.compile(r"(?<!\d)(\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?){0,2}\s*kV)\b", re.IGNORECASE),
    "power": re.compile(r"(?<!\d)(\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?\s*(?:MVA|kVA|MW))\b", re.IGNORECASE),
    "reactive": re.compile(r"([+\-±]?\s*\d+(?:\.\d+)?\s*MVAr)\b", re.IGNORECASE),
    "current": re.compile(r"(?<![/\d])(\d+(?:\.\d+)?\s*A)\b", re.IGNORECASE),
    "short_circuit": re.compile(r"(\d+(?:\.\d+)?\s*kA.{0,80}?(?:\d+(?:\.\d+)?|ONE|TWO|THREE)\s*(?:s|sec|seconds?))", re.IGNORECASE),
    "frequency": re.compile(r"(\d+(?:\.\d+)?\s*Hz)\b", re.IGNORECASE),
    "temperature": re.compile(r"(\d+(?:\.\d+)?\s*(?:°\s*C|º\s*C|deg(?:ree)?s?\s*C|C\b))", re.IGNORECASE),
    "percent": re.compile(r"([+\-]?\d+(?:\.\d+)?\s*%)"),
    "resistance": re.compile(r"(\d+(?:\.\d+)?\s*(?:ohms?|Ω))", re.IGNORECASE),
    "burden": re.compile(r"(\d+(?:\.\d+)?\s*VA)\b", re.IGNORECASE),
    "class": re.compile(r"(?:\bCLASS\b|\bCL\.)\s*([A-Z0-9.]+(?:\s*[/+]\s*[A-Z0-9.]+)?)", re.IGNORECASE),
    "vector": re.compile(r"\b((?:Y|D|Z|N|y|d|z|n){2,8}\d{0,2}(?:\s*\+?\s*d\d+)?)\b"),
    "oltc": re.compile(r"OLTC.{0,120}", re.IGNORECASE),
    "quantity": re.compile(
        r"(?:QTY|QUANTITY|NOS?\.?|NO\.?|EACH)\s*[:\-]?\s*(\d+)"
        r"|\b(\d+)\s*(?:NOS?\.?|UNITS?|BAYS?|PANELS?|SETS?|EACH)\b",
        re.IGNORECASE,
    ),
}

CLAUSE_RE = re.compile(r"\b(\d+(?:\.\d+){1,4}[A-Z]?(?:\.[A-Z0-9]+)*)\b", re.IGNORECASE)
TMSS_RE = re.compile(r"\b(\d{2}-(?:TMSS|SDMS)-\d{2})\b", re.IGNORECASE)
TES_RE = re.compile(r"\b(TES-[A-Z]-\d+(?:\.\d+)*)\b", re.IGNORECASE)
APPENDIX_RE = re.compile(r"\bAPPENDIX\s*(?:#\s*)?([A-Z0-9IVX-]+)?", re.IGNORECASE)


def normalize_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = text.replace("–", "-").replace("—", "-")
    text = text.replace("º", "°")
    text = re.sub(r"\s+", " ", text)
    return text.strip().upper()


def normalize_value(value: str) -> str:
    value = normalize_text(value)
    value = value.replace("OHMS", "Ω").replace("OHM", "Ω")
    value = re.sub(r"\s*([/:,;+\-])\s*", r"\1", value)
    value = re.sub(r"\s+(KV|KA|A|MVA|KVA|MW|MVAR|HZ|VA|SEC|S)\b", r"\1", value)
    return value


def tokenise(text: str) -> set[str]:
    return set(re.findall(r"[A-Z0-9]+(?:\.\d+)?", normalize_text(text)))


def meaningful_tokens(*parts: str) -> list[str]:
    raw: list[str] = []
    for part in parts:
        if not part:
            continue
        raw.extend(re.findall(r"[A-Z0-9]+(?:\.\d+)?", normalize_text(part)))
    result = []
    seen = set()
    for token in raw:
        if len(token) < 2 or token in STOP_WORDS:
            continue
        if token not in seen:
            result.append(token)
            seen.add(token)
    return result


def alias_phrases(text: str) -> list[str]:
    key = normalize_text(text)
    phrases = [key] if key else []
    for alias_key, aliases in ALIASES.items():
        if alias_key in key or key in alias_key:
            phrases.extend(aliases)
    # preserve order / uniqueness
    out = []
    seen = set()
    for phrase in phrases:
        p = normalize_text(phrase)
        if p and p not in seen:
            out.append(p)
            seen.add(p)
    return out


# ---------------------------------------------------------------------------
# Template I/O
# ---------------------------------------------------------------------------

class SLDTemplate:
    """Read the fixed A/B/C hierarchy and write D/E/F output values."""

    def __init__(self, template_path: str | Path):
        self.template_path = Path(template_path)
        if not self.template_path.exists():
            raise FileNotFoundError(f"SLD template not found: {self.template_path}")

    def load_rows(self) -> list[TemplateRow]:
        wb = load_workbook(self.template_path, data_only=False)
        if "SLD" not in wb.sheetnames:
            raise ValueError("Template must contain a worksheet named 'SLD'.")
        ws = wb["SLD"]

        rows: list[TemplateRow] = []
        inherited_section = ""
        inherited_component = ""

        # Row 1 is project name, row 2 is header. A/B/C are the fixed template.
        for row_num in range(3, ws.max_row + 1):
            section_display = str(ws.cell(row_num, 1).value or "").strip()
            component_display = str(ws.cell(row_num, 2).value or "").strip()
            parameter = str(ws.cell(row_num, 3).value or "").strip()

            if section_display:
                inherited_section = section_display
                inherited_component = ""
            if component_display:
                inherited_component = component_display

            if not (inherited_section or inherited_component or parameter):
                continue
            if not parameter:
                # Section/grouping row with no actual parameter to resolve.
                continue

            rows.append(
                TemplateRow(
                    excel_row=row_num,
                    section_display=section_display,
                    component_display=component_display,
                    parameter=parameter,
                    section=inherited_section,
                    component=inherited_component,
                )
            )
        return rows

    def create_output(
        self,
        output_path: str | Path,
        project_name: str,
        results: dict[int, ExtractionResult],
    ) -> None:
        wb = load_workbook(self.template_path)
        if "SLD" not in wb.sheetnames:
            raise ValueError("Template must contain a worksheet named 'SLD'.")
        ws = wb["SLD"]

        ws["A1"] = project_name

        # The output contract is strict: A/B/C stay fixed. D/E/F are generated.
        # G is reserved for manual notes and is always blank in generated files.
        for row_num in range(3, ws.max_row + 1):
            ws.cell(row_num, 4).value = None
            ws.cell(row_num, 5).value = None
            ws.cell(row_num, 6).value = None
            ws.cell(row_num, 7).value = None

        for row_num, result in results.items():
            ws.cell(row_num, 4).value = result.value
            ws.cell(row_num, 5).value = result.pages
            ws.cell(row_num, 6).value = result.reference
            ws.cell(row_num, 7).value = None

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(output_path)


# ---------------------------------------------------------------------------
# PDF index
# ---------------------------------------------------------------------------

class PDFIndex:
    """One-pass physical-page index for fast repeated lookups."""

    def __init__(self, pages: list[IndexedPage]):
        self.pages = pages
        self.by_token: dict[str, set[int]] = {}
        self.by_number: dict[int, IndexedPage] = {p.page_number: p for p in pages}
        self.main_pages: list[IndexedPage] = [p for p in pages if p.source_priority == 0]
        for page in pages:
            for token in page.tokens:
                self.by_token.setdefault(token, set()).add(page.page_number)

    @classmethod
    def build(
        cls,
        processor: PDFProcessor,
        start_page: int = 1,
        end_page: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        stop_callback: Optional[Callable[[], bool]] = None,
        intermediate_dir: Optional[Path] = None,
    ) -> "PDFIndex":
        total_pages = processor.get_total_pages()
        actual_start = max(1, start_page)
        actual_end = min(end_page or total_pages, total_pages)
        selected_total = actual_end - actual_start + 1

        pages: list[IndexedPage] = []
        for count, (page_num, text, _tables) in enumerate(
            processor.extract_text_pages(actual_start - 1, actual_end, extract_tables=False),
            start=1,
        ):
            if stop_callback and stop_callback():
                raise InterruptedError("Extraction cancelled by user.")

            lines = [line.strip() for line in text.splitlines() if line.strip()]
            normalized = normalize_text(text)
            page = IndexedPage(
                page_number=page_num,
                text=text,
                normalized=normalized,
                lines=lines,
                line_norms=[normalize_text(line) for line in lines],
                line_tokens=[tokenise(line) for line in lines],
                tokens=tokenise(text),
            )
            pages.append(page)

            if intermediate_dir is not None and text:
                intermediate_dir.mkdir(parents=True, exist_ok=True)
                (intermediate_dir / f"page_{page_num:04d}.txt").write_text(text, encoding="utf-8")

            if progress_callback:
                progress_callback(count, selected_total)

        cls._classify_sources(pages)
        return cls(pages)

    @staticmethod
    def _classify_sources(pages: list[IndexedPage]) -> None:
        """Classify Main SOW / project appendices / generic standards.

        The Main SOW boundary is detected from the first standalone appendix
        title (for example ``APPENDIX - I``), not from the document's printed
        page numbering. This works even when printed numbering restarts or uses
        different conventions in other specifications.
        """
        first_appendix_page = None
        first_appendix_re = re.compile(r"^\s*APPENDIX\s*[-#]?\s*(?:I|1|A)\s*$", re.IGNORECASE)
        any_appendix_re = re.compile(r"^\s*APPENDIX\s*[-#]?\s*[A-Z0-9IVX]+\s*$", re.IGNORECASE)

        for page in pages:
            if any(first_appendix_re.match(line) for line in page.lines):
                first_appendix_page = page.page_number
                break
        if first_appendix_page is None:
            for page in pages[5:]:
                if any(any_appendix_re.match(line) for line in page.lines):
                    first_appendix_page = page.page_number
                    break

        main_sow_end = first_appendix_page - 1 if first_appendix_page else None

        for page in pages:
            n = page.normalized
            is_tmss_title = "TRANSMISSION MATERIALS STANDARD SPECIFICATION" in n
            has_data_schedule = "DATA SCHEDULE" in n
            appendix_title = any(
                re.match(r"^\s*APPENDIX\s*[-#]?\s*[A-Z0-9IVX-]+", line, re.IGNORECASE)
                for line in page.lines[:30]
            )

            if is_tmss_title and has_data_schedule:
                page.source_kind = "DATA_SCHEDULE"
                page.source_priority = 2
            elif is_tmss_title:
                page.source_kind = "GENERIC_SPEC"
                page.source_priority = 3
            elif main_sow_end is not None and page.page_number <= main_sow_end:
                page.source_kind = "MAIN_SOW"
                page.source_priority = 0
            elif appendix_title or first_appendix_page is not None:
                page.source_kind = "PROJECT_APPENDIX"
                page.source_priority = 1
            else:
                # A standalone PTS excerpt with no appendix structure is treated
                # as project-specific Main SOW content.
                page.source_kind = "MAIN_SOW"
                page.source_priority = 0


    def candidate_pages(self, row: TemplateRow, limit: int = 12) -> list[IndexedPage]:
        """Return a small, high-value page set for one template row.

        The previous implementation unioned every query-token posting list,
        which could expand to almost the whole document for common engineering
        words. Here we start from the rarest indexed tokens and intersect while
        possible, then rank only that compact set.
        """
        tokens = meaningful_tokens(row.section, row.component, row.parameter)

        expanded_tokens = list(tokens)
        for phrase in alias_phrases(row.section) + alias_phrases(row.component) + alias_phrases(row.parameter):
            expanded_tokens.extend(meaningful_tokens(phrase))

        # De-duplicate and keep only tokens that actually exist in the index.
        seen = set()
        token_sets = []
        for token in expanded_tokens:
            if token in seen:
                continue
            seen.add(token)
            pages = self.by_token.get(token)
            if pages:
                token_sets.append((token, pages))

        if not token_sets:
            return []

        token_sets.sort(key=lambda item: len(item[1]))
        candidate_numbers = set(token_sets[0][1])

        # Intersect rare terms when that keeps at least one result. This makes
        # queries like GIS + BUS + COUPLER much more selective than a union.
        for _token, page_set in token_sets[1:6]:
            inter = candidate_numbers.intersection(page_set)
            if inter:
                candidate_numbers = inter
            if len(candidate_numbers) <= max(limit * 2, 40):
                break

        # If the rarest token was still very broad, add pages from the next
        # rare terms so that alternative wording is not accidentally lost.
        if len(candidate_numbers) < min(8, limit):
            for _token, page_set in token_sets[1:4]:
                candidate_numbers.update(page_set)
                if len(candidate_numbers) >= limit * 3:
                    break

        section_phrases = alias_phrases(row.section)
        component_phrases = alias_phrases(row.component)
        parameter_phrases = [] if normalize_text(row.parameter) in GENERIC_PARAMETERS else alias_phrases(row.parameter)

        # Always give project-specific Main SOW pages a chance. The document may
        # use different wording than an appendix/TMSS, and source priority must
        # not be defeated by token-index pruning.
        main_scored = []
        for page in self.main_pages:
            score = 0
            component_hit = any(phrase and phrase in page.normalized for phrase in component_phrases)
            section_hit = any(phrase and phrase in page.normalized for phrase in section_phrases)
            score += 3 * sum(1 for phrase in component_phrases if phrase and phrase in page.normalized)
            score += 2 * sum(1 for phrase in section_phrases if phrase and phrase in page.normalized)
            score += 4 * sum(1 for phrase in parameter_phrases if phrase and phrase in page.normalized)
            # Main equipment schedules are the authoritative project-specific
            # source in National Grid PTS documents. Reward pages that look like
            # an item/QTY/description schedule when they also name the target.
            if section_hit:
                longest_section_hit = max((len(ph) for ph in section_phrases if ph and ph in page.normalized), default=0)
                score += min(20, longest_section_hit / 2)
            if section_hit and ("ITEM #" in page.normalized or "QTY" in page.tokens or "QUANTITY" in page.tokens):
                score += 20
            if component_hit and "DESCRIPTION" in page.tokens:
                score += 5
            if score:
                main_scored.append((score, page.page_number))
        main_scored.sort(key=lambda item: (-item[0], item[1]))
        candidate_numbers.update(page_number for _score, page_number in main_scored[:30])

        ranked = []
        base_tokens = meaningful_tokens(row.section, row.component, row.parameter)
        for page_number in candidate_numbers:
            page = self.by_number[page_number]
            hits = sum(1 for token in base_tokens if token in page.tokens)
            phrase_hits = 0
            phrase_hits += 3 * sum(1 for phrase in component_phrases if phrase and phrase in page.normalized)
            phrase_hits += 2 * sum(1 for phrase in section_phrases if phrase and phrase in page.normalized)
            phrase_hits += 4 * sum(1 for phrase in parameter_phrases if phrase and phrase in page.normalized)
            longest_section_hit = max((len(ph) for ph in section_phrases if ph and ph in page.normalized), default=0)
            phrase_hits += min(12, longest_section_hit / 3)
            if longest_section_hit and ("ITEM #" in page.normalized or "QTY" in page.tokens or "QUANTITY" in page.tokens):
                phrase_hits += 12
            ranked.append((hits + phrase_hits, -page.source_priority, -page_number, page))

        ranked.sort(reverse=True, key=lambda item: (item[0], item[1], item[2]))

        # Never let high keyword density in a generic appendix push all Main
        # SOW pages out of the candidate window. Reserve a source-priority
        # quota, then fill the remaining slots by relevance.
        main_ranked = [item for item in ranked if item[3].source_priority == 0][:12]
        other_ranked = [item for item in ranked if item[3].source_priority != 0]
        selected = list(main_ranked)
        selected_pages = {item[3].page_number for item in selected}
        for item in other_ranked:
            if len(selected) >= max(limit, 20):
                break
            if item[3].page_number not in selected_pages:
                selected.append(item)
                selected_pages.add(item[3].page_number)
        return [item[3] for item in selected]


# ---------------------------------------------------------------------------
# Extraction logic
# ---------------------------------------------------------------------------

class SLDTemplateExtractor:
    def __init__(self, pdf_index: PDFIndex, pdf_path: str | Path):
        self.index = pdf_index
        self.pdf_path = Path(pdf_path)

    def extract_project_name(self) -> str:
        # Prefer a title block assembled from adjacent early-page lines. This
        # handles project names split across two PDF text lines.
        for page in self.index.pages[: min(10, len(self.index.pages))]:
            lines = [re.sub(r"\s+", " ", line).strip(" -") for line in page.lines]
            for idx, line in enumerate(lines):
                upper = line.upper()
                if "POWER SUPPLY" in upper and "PROJECT" in upper:
                    title = line
                    if idx + 1 < len(lines):
                        nxt = lines[idx + 1]
                        if any(k in nxt.upper() for k in ["SWPC", "SHOAIBA", "SUBSTATION", "PROJECT", "MAKKAH", "JEDDAH"]):
                            title = f"{title} {nxt}"
                    if 12 <= len(title) <= 180:
                        return title

        candidates: list[tuple[int, str]] = []
        for page in self.index.pages[: min(15, len(self.index.pages))]:
            for line in page.lines:
                cleaned = re.sub(r"\s+", " ", line).strip(" -")
                upper = cleaned.upper()
                if len(cleaned) < 12 or len(cleaned) > 160:
                    continue
                score = 0
                if "PROJECT" in upper:
                    score += 5
                if "SUBSTATION" in upper:
                    score += 4
                if "POWER SUPPLY" in upper:
                    score += 3
                if cleaned.startswith(("•", "-")):
                    score -= 4
                if any(x in upper for x in ["DRAWING CONTROL", "REVISION", "PAGE NO", "JOB ORDER", "WILL CONSTRUCT"]):
                    score -= 6
                if score > 0:
                    candidates.append((score, cleaned))
        if candidates:
            candidates.sort(key=lambda x: (x[0], len(x[1])), reverse=True)
            return candidates[0][1]
        return self.pdf_path.stem

    def extract_rows(
        self,
        template_rows: Iterable[TemplateRow],
        progress_callback: Optional[Callable[[int, int], None]] = None,
        stop_callback: Optional[Callable[[], bool]] = None,
    ) -> dict[int, ExtractionResult]:
        rows = list(template_rows)
        results: dict[int, ExtractionResult] = {}
        total = len(rows)
        for idx, row in enumerate(rows, start=1):
            if stop_callback and stop_callback():
                raise InterruptedError("Extraction cancelled by user.")
            results[row.excel_row] = self.extract_row(row)
            if progress_callback:
                progress_callback(idx, total)
        return results

    def extract_row(self, row: TemplateRow) -> ExtractionResult:
        candidates: list[ExtractionCandidate] = []
        if normalize_text(row.section) == "OTHER TYPICAL SLD COMPONENTS":
            phrases = alias_phrases(row.component)
            pages = [
                p for p in self.index.main_pages
                if any(ph and ph in p.normalized for ph in phrases)
            ][:12]
        else:
            pages = self.index.candidate_pages(row)
        for page in pages:
            candidates.extend(self._extract_from_page(row, page))

        if not candidates:
            return ExtractionResult()

        # Group equivalent values. Conflicts are resolved by the best source
        # priority first (Main SOW = 0), then relevance score.
        groups: dict[str, list[ExtractionCandidate]] = {}
        for candidate in candidates:
            key = normalize_value(candidate.value)
            if not key:
                continue
            groups.setdefault(key, []).append(candidate)
        if not groups:
            return ExtractionResult()

        # When a complete multi-stage cooling designation exists, do not let a
        # nearby standalone word (e.g. ONAN in a losses sentence) replace it.
        if "COOLING" in normalize_text(row.parameter):
            multi_stage = {k: v for k, v in groups.items() if "/" in k}
            if multi_stage:
                groups = multi_stage

        def group_rank(items: list[ExtractionCandidate]) -> tuple[int, float, int]:
            return (
                min(c.source_priority for c in items),
                -max(c.score for c in items),
                min(c.page_number for c in items),
            )

        winning = min(groups.values(), key=group_rank)
        representative = max(winning, key=lambda c: c.score)
        # Keep all *relevant candidate* pages that produced the same winning
        # value. We intentionally do not scan the whole PDF for a generic literal
        # such as "13.8 kV", which would create hundreds of irrelevant pages.
        best_priority = min(c.source_priority for c in winning)
        best_score = max(c.score for c in winning if c.source_priority == best_priority)
        relevant_winning = [
            c for c in winning
            if c.source_priority <= max(1, best_priority) and c.score >= best_score - 2.5
        ]
        pages = sorted({c.page_number for c in relevant_winning})
        references = []
        for c in sorted(relevant_winning, key=lambda x: (x.source_priority, x.page_number)):
            if c.reference and c.reference not in references:
                references.append(c.reference)

        return ExtractionResult(
            value=representative.value.strip(),
            pages="; ".join(str(p) for p in pages),
            reference="; ".join(references) if references else "NA",
        )

    # ------------------------- page candidate extraction ------------------

    def _extract_from_page(self, row: TemplateRow, page: IndexedPage) -> list[ExtractionCandidate]:
        if normalize_text(row.section) == "OTHER TYPICAL SLD COMPONENTS" and page.source_priority > 1:
            return []
        if not self._page_has_section_context(row, page):
            return []
        line_indices = self._relevant_line_indices(row, page)
        if not line_indices:
            return []

        out: list[ExtractionCandidate] = []
        seen = set()
        for idx, base_score in line_indices[:14]:
            window_start = max(0, idx - 2)
            window_end = min(len(page.lines), idx + 3)
            window = " | ".join(page.lines[window_start:window_end])
            values = self._extract_values_for_row(row, window, page.lines[idx])
            for value, extra_score in values:
                value = self._clean_value(value)
                if not value or value.upper() in {"N/A", "NA"}:
                    continue
                key = normalize_value(value)
                if key in seen:
                    continue
                seen.add(key)
                reference = self._derive_reference(page, idx)
                authority_bonus = self._page_authority_bonus(row, page)
                line_penalty = self._reference_list_penalty(page.lines[idx])
                out.append(
                    ExtractionCandidate(
                        value=value,
                        page_number=page.page_number,
                        reference=reference,
                        source_priority=page.source_priority,
                        score=base_score + extra_score + authority_bonus - line_penalty,
                    )
                )
        return out

    def _page_authority_bonus(self, row: TemplateRow, page: IndexedPage) -> float:
        """Reward explicit project equipment schedules over generic reference lists."""
        if page.source_priority != 0:
            return 0.0
        section_phrases = alias_phrases(row.section)
        matched = [ph for ph in section_phrases if ph and ph in page.normalized]
        if not matched:
            return 0.0
        longest = max(matched, key=len)
        bonus = min(12.0, len(longest) / 2.0)
        if "ITEM #" in page.normalized or ("QTY" in page.tokens and "DESCRIPTION" in page.tokens):
            bonus += 30.0
        # Some project equipment clauses are prose schedules (e.g.
        # "Two (2) nos. each: 1000 kVA ...") rather than tables.
        if re.search(r"\b(?:ONE|TWO|THREE|FOUR)\s*\(\d+\)\s*NOS?\.?\s+EACH", page.normalized, re.I):
            bonus += 24.0
        return bonus

    @staticmethod
    def _reference_list_penalty(line: str) -> float:
        upper = normalize_text(line)
        if ("TMSS" in upper or "TES-" in upper or "SDMS" in upper) and any(
            marker in upper for marker in ["REV", "RATED ABOVE", "UP TO", "THROUGH"]
        ):
            return 25.0
        return 0.0

    def _relevant_line_indices(self, row: TemplateRow, page: IndexedPage) -> list[tuple[int, float]]:
        section_phrases = alias_phrases(row.section)
        component_phrases = alias_phrases(row.component)
        param_norm_global = normalize_text(row.parameter)
        param_phrases = [] if param_norm_global in GENERIC_PARAMETERS else alias_phrases(row.parameter)
        param_tokens = meaningful_tokens(row.parameter)
        component_tokens = meaningful_tokens(row.component)
        section_tokens = meaningful_tokens(row.section)

        ranked: list[tuple[int, float]] = []
        for idx, line_norm in enumerate(page.line_norms):
            line_tokens = page.line_tokens[idx]
            nearby_slice = range(max(0, idx - 4), min(len(page.line_norms), idx + 5))
            nearby_norm = " ".join(page.line_norms[j] for j in nearby_slice)
            nearby_tokens = set().union(*(page.line_tokens[j] for j in nearby_slice)) if page.line_tokens else set()

            context_score = 0.0
            if any(phrase and phrase in line_norm for phrase in component_phrases):
                context_score += 5.0
            if any(phrase and phrase in line_norm for phrase in section_phrases):
                context_score += 4.0
            if any(phrase and phrase in nearby_norm for phrase in component_phrases):
                context_score += 3.0
            if any(phrase and phrase in nearby_norm for phrase in section_phrases):
                context_score += 2.5
            context_score += 1.5 * sum(1 for tok in component_tokens if tok in nearby_tokens)
            context_score += 1.0 * sum(1 for tok in section_tokens if tok in nearby_tokens)

            # Do not extract a generic number merely because the page contains
            # the section somewhere else. The value line must be locally tied
            # to the requested section/component.
            if context_score <= 0 and normalize_text(row.section) not in {"REMOTE END", "OTHER TYPICAL SLD COMPONENTS"}:
                continue

            score = context_score
            if any(phrase and phrase in line_norm for phrase in param_phrases):
                score += 15.0
            score += 2.5 * sum(1 for tok in param_tokens if tok in line_tokens)
            score += 1.5 * sum(1 for tok in param_tokens if tok in nearby_tokens)

            param_norm = normalize_text(row.parameter)
            if param_norm and param_norm not in GENERIC_PARAMETERS and param_norm in nearby_norm:
                score += 15.0

            # A line that already contains a value of the expected engineering
            # type is more useful than a line that only repeats a parameter label.
            if self._line_has_expected_value(row, page.lines[idx]):
                score += 8.0

            if score >= 3.0:
                ranked.append((idx, score))

        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked

    def _extract_values_for_row(self, row: TemplateRow, window: str, focus_line: str) -> list[tuple[str, float]]:
        p = normalize_text(row.parameter)
        c = normalize_text(row.component)
        combined = f"{c} {p}"
        text = window
        values: list[tuple[str, float]] = []

        if "ARRANGEMENT" in p:
            m = re.search(r"\b(DOUBLE\s+BUS(?:BAR)?(?:\s+SINGLE\s+BREAKER)?|SINGLE\s+BUS(?:BAR)?|DOUBLE\s+BUS(?:BAR)?)\b", text, re.IGNORECASE)
            if m:
                return [(m.group(1), 6.0)]
            return []

        if p == "TYPE" and ("VT" in c or "VOLTAGE TRANSFORMER" in c):
            if re.search(r"THREE[-\s]*PHASE", text, re.IGNORECASE):
                return [("3-Phase Inductive", 5.0)]
            return []

        # Quantities / counts
        if self._is_quantity_parameter(row):
            quantities = self._extract_quantity(focus_line, row)
            if not quantities:
                quantities = self._extract_quantity(text, row, allow_context=True)
            values.extend((v, 4.0) for v in quantities)
            return values

        # CT-related rows. Use token/phrase matching; substring matching would
        # incorrectly classify words such as VECTOR as CT data.
        has_ct = bool(re.search(r"\bCT\b|CURRENT TRANSFORMER|BUSHING CT", combined, re.IGNORECASE))
        if has_ct:
            for match in VALUE_PATTERNS["ct"].finditer(text):
                ratio = match.group("ratio") or ""
                rest = match.group("rest") or ""
                value = f"{ratio} {rest}".strip(" ,;|")
                if ratio:
                    values.append((value, 5.0))
            return values

        # VT-related rows.
        has_vt = bool(re.search(r"\bVT\b|VOLTAGE TRANSFORMER|POTENTIAL TRANSFORMER|GIB VT", combined, re.IGNORECASE))
        if has_vt:
            for match in VALUE_PATTERNS["vt"].finditer(text):
                values.append((match.group("value"), 5.0))
            if "BURDEN" in p:
                burdens = VALUE_PATTERNS["burden"].findall(text)
                if burdens:
                    values.append((" + ".join(dict.fromkeys(burdens)), 4.5))
            if "CLASS" in p:
                classes = [cval for cval in VALUE_PATTERNS["class"].findall(text)
                           if re.search(r"\d|PX|P$", cval, re.IGNORECASE)]
                if classes:
                    values.append((" / ".join(dict.fromkeys(classes)), 4.5))
            return values

        if "VECTOR" in p:
            out = []
            for m in VALUE_PATTERNS["vector"].finditer(text):
                value = m.group(1)
                # Real transformer vector groups contain a clock number; this
                # rejects incidental abbreviations such as E&DD.
                if re.search(r"\d", value):
                    out.append((value, 6.0))
            return out

        if "OLTC" in p:
            m = re.search(r"OLTC.{0,50}?([+]?\d+(?:\.\d+)?\s*%\s*(?:TO|-)\s*-?\d+(?:\.\d+)?\s*%).{0,50}?(?:STEP(?:\s+VOLTAGE)?\s*)?(\d+(?:\.\d+)?\s*%)?", text, re.IGNORECASE)
            if m:
                value = m.group(1)
                if m.group(2):
                    value += f", Step {m.group(2)}"
                return [(value, 6.0)]
            return []

        if "REACTIVE POWER" in p or "MVAR" in combined:
            found = VALUE_PATTERNS["reactive"].findall(text)
            if found:
                # Preserve both capacitive/inductive endpoints when stated.
                uniq = list(dict.fromkeys(re.sub(r"\s+", " ", x).strip() for x in found))
                if len(uniq) >= 2:
                    return [(" / ".join(uniq[:2]), 6.0)]
                return [(uniq[0], 5.0)]
            return []

        if p == "POWER" or "POWER" in p:
            return [(m, 5.0) for m in VALUE_PATTERNS["power"].findall(text)]

        if p == "VOLTAGE" or "VOLTAGE" in p or "BIL" in p or "WITHSTAND" in p:
            return [(m, 4.5) for m in VALUE_PATTERNS["voltage"].findall(text)]

        if "FREQUENCY" in p:
            return [(m, 5.0) for m in VALUE_PATTERNS["frequency"].findall(text)]

        if "AMBIENT" in p or "TEMPERATURE" in p:
            return [(m, 5.0) for m in VALUE_PATTERNS["temperature"].findall(text)]

        if "RESISTANCE" in p:
            return [(m, 5.0) for m in VALUE_PATTERNS["resistance"].findall(text)]

        if "BUILT-IN EQUIPMENT" in p:
            upper = normalize_text(text)
            if ("DS" in tokenise(upper) or "DISCONNECT" in upper) and "CT" in tokenise(upper):
                return [("DS + CT", 6.0)]
            return []

        if "CURRENT / TIME" in p:
            m = re.search(r"(\d+(?:\.\d+)?\s*A).{0,40}?(\d+(?:\.\d+)?\s*(?:s|sec|seconds?))", text, re.IGNORECASE)
            if m:
                return [(f"{m.group(1)} / {m.group(2)}", 6.0)]
            return []

        if "SHORT CIRCUIT" in p:
            short = VALUE_PATTERNS["short_circuit"].findall(text)
            if short:
                return [(m, 5.0) for m in short]

        if "OVERLOAD" in p:
            percents = VALUE_PATTERNS["percent"].findall(text)
            seconds = re.findall(r"\b\d+(?:\.\d+)?\s*(?:s|sec|seconds?)\b", text, re.IGNORECASE)
            if percents:
                value = percents[0]
                if seconds:
                    value += f" for {seconds[0]}"
                return [(value, 5.0)]

        if "IMPEDANCE" in p:
            m = re.search(r"(?:WITH\s+)?(\d+(?:\.\d+)?\s*%).{0,12}?IMPEDANCE|IMPEDANCE.{0,35}?(\d+(?:\.\d+)?\s*%)", text, re.IGNORECASE)
            if m:
                return [((m.group(1) or m.group(2)), 6.0)]
            return []

        if "COOLING" in p:
            cooling = re.findall(r"\b(?:ONAN|ONAF|OFAF|ODAF|AN|AF)(?:\s*/\s*(?:ONAN|ONAF|OFAF|ODAF|AN|AF))*\b", text, re.IGNORECASE)
            if not cooling:
                return []
            # Prefer the complete dual-stage cooling designation (e.g.
            # ONAN/ONAF) over a nearby standalone occurrence of ONAN.
            cooling = list(dict.fromkeys(cooling))
            longest = max(cooling, key=lambda x: (x.count("/"), len(x)))
            return [(longest, 8.0 if "/" in longest else 5.0)]

        if normalize_text(row.section) == "SWGR" and c == "RATING" and p == "SYSTEM":
            volts = VALUE_PATTERNS["voltage"].findall(text)
            return [(m, 6.0) for m in volts]

        if normalize_text(row.section) == "SWGR" and c == "RATING" and p == "MAIN BUS":
            currents = VALUE_PATTERNS["current"].findall(text)
            return [(m, 6.0) for m in currents if self._reasonable_amp_value(m)]

        if (p == "CB" or " CB" in f" {c}" or c == "CB") and "SHORT CIRCUIT" not in p:
            focus_currents = VALUE_PATTERNS["current"].findall(focus_line)
            focus_currents = [m for m in focus_currents if self._reasonable_amp_value(m)]
            if focus_currents:
                return [(m, 8.0) for m in focus_currents]
            currents = VALUE_PATTERNS["current"].findall(text)
            return [(m, 5.0) for m in currents if self._reasonable_amp_value(m)]

        if "EARTH SW" in c and "RATING" in p:
            currents = VALUE_PATTERNS["current"].findall(text)
            return [(m, 5.0) for m in currents if self._reasonable_amp_value(m)]

        if p == "SA" or c == "SA":
            volts = VALUE_PATTERNS["voltage"].findall(text)
            return [(m, 5.0) for m in volts]

        # Generic equipment rating: prefer compact engineering phrases from
        # the focus line/window, with units appropriate to the component.
        if "RATING" in p or p in {"SYSTEM", "MAIN BUS", "CB", "CLASS", "BURDEN / CLASS"}:
            return self._extract_generic_rating(row, focus_line, window)

        # Final fallback: one compact value near the focused context.
        return self._extract_generic_rating(row, focus_line, window)

    def _extract_generic_rating(self, row: TemplateRow, focus_line: str, window: str) -> list[tuple[str, float]]:
        text = f"{focus_line} | {window}"
        component = normalize_text(row.component)
        parameter = normalize_text(row.parameter)
        patterns = []

        if any(k in component for k in ["CB", "EARTH", "GIB", "BUS", "FEEDER", "SWGR"]):
            patterns.extend(["short_circuit", "current", "voltage"])
        elif any(k in component for k in ["TRANSFORMER", "STATCOM"]):
            patterns.extend(["power", "reactive", "voltage", "percent"])
        elif "SA" in component or "ARRESTER" in component:
            patterns.extend(["voltage", "current"])
        elif "CABLE" in component:
            # Cable size / construction patterns first, preferring the focused
            # line so a neighbouring circuit's cable size is not selected.
            cable_re = r"\b(?:\d+\s*[xX×]\s*)?(?:\d+\s*C\s*[xX×]\s*)?\d+\s*mm(?:²|2)\b"
            cable = re.findall(cable_re, focus_line, re.IGNORECASE)
            if not cable:
                cable = re.findall(cable_re, text, re.IGNORECASE)
            if cable:
                return [(m, 6.0) for m in cable]
            patterns.extend(["voltage", "current"])
        else:
            patterns.extend(["voltage", "current", "power", "reactive", "frequency", "percent", "resistance"])

        values = []
        for name in patterns:
            pattern = VALUE_PATTERNS[name]
            found = pattern.findall(text)
            for item in found:
                if isinstance(item, tuple):
                    item = next((x for x in item if x), "")
                if item:
                    values.append((str(item), 2.5))
        return values[:8]

    def _extract_quantity(self, text: str, row: TemplateRow, allow_context: bool = False) -> list[str]:
        normalized = normalize_text(text)

        # For hierarchy rows such as GIS/Bays/OHL Feeder, the parameter is the
        # actual equipment target. Otherwise the Component is the target.
        target = row.parameter if normalize_text(row.component) in {"BAYS", "NO.", "FEEDER NO."} else row.component
        target_phrases = alias_phrases(target)

        # Prefer a count that occurs after the target heading in the same small
        # text window. This prevents a total-bay count from being assigned to an
        # individual OHL/Cable/Transformer feeder row.
        for phrase in target_phrases:
            pos = normalized.find(phrase)
            if pos < 0:
                continue
            before = normalized[max(0, pos - 160):pos]
            # Equipment schedules commonly place Unit/QTY before the description:
            # "Each 4 OHL feeder modules ...". Prefer that quantity.
            m_before = re.search(r"\bEACH\s+(\d+)\s*$", before, re.IGNORECASE)
            if not m_before:
                m_before = re.search(r"\bEACH\s+(\d+)\b.{0,80}$", before, re.IGNORECASE)
            if m_before:
                return [m_before.group(1)]
            after = normalized[pos: pos + 140]
            patterns = [
                r"\bEACH\s+(\d+)\b",
                r"\b(?:ONE|TWO|THREE|FOUR)?\s*\((\d+)\)\s*NOS?\.?\b",
                r"\b(\d+)\s*NOS?\.?\b",
                r"\b(\d+)\s*(?:UNITS?|BAYS?|PANELS?|SETS?)\b",
            ]
            for pattern in patterns:
                m = re.search(pattern, after, re.IGNORECASE)
                if m:
                    return [m.group(1)]

        # Explicit QTY fields are safe fallbacks.
        for pattern in [
            r"\b(?:QTY|QUANTITY)\s*[:=\-]?\s*(\d+)\b",
            r"\bEACH\s+(\d+)\b",
        ]:
            m = re.search(pattern, normalized, re.IGNORECASE)
            if m:
                return [m.group(1)]

        return []

    def _is_quantity_parameter(self, row: TemplateRow) -> bool:
        p = normalize_text(row.parameter)
        c = normalize_text(row.component)
        if p in {"NO.", "NO", "MAIN", "FUTURE", "SPARE", "OHL FEEDER", "CABLE FEEDER", "TRANSFORMER FEEDER", "BUS COUPLER", "BUS SECTION", "SPARE EQUIPPED", "BUS VT MODULE"}:
            return True
        if p.endswith(" NO.") or p.endswith(" NO"):
            return True
        if c in {"BAYS", "NO.", "FEEDER NO."}:
            return True
        return False

    def _line_has_expected_value(self, row: TemplateRow, line: str) -> bool:
        p = normalize_text(row.parameter)
        c = normalize_text(row.component)
        combined = f"{c} {p}"
        if re.search(r"\bCT\b|CURRENT TRANSFORMER|BUSHING CT", combined, re.IGNORECASE):
            return bool(VALUE_PATTERNS["ct"].search(line))
        if re.search(r"\bVT\b|VOLTAGE TRANSFORMER|POTENTIAL TRANSFORMER|GIB VT", combined, re.IGNORECASE):
            return bool(VALUE_PATTERNS["vt"].search(line))
        if "VECTOR" in p:
            return bool(VALUE_PATTERNS["vector"].search(line))
        if "OLTC" in p:
            return bool(VALUE_PATTERNS["oltc"].search(line))
        if "FREQUENCY" in p:
            return bool(VALUE_PATTERNS["frequency"].search(line))
        if "COOLING" in p:
            return bool(re.search(r"\b(?:ONAN|ONAF|OFAF|ODAF|AN|AF)(?:\s*/\s*(?:ONAN|ONAF|OFAF|ODAF|AN|AF))*\b", line, re.I))
        if "IMPEDANCE" in p:
            return "IMPEDANCE" in normalize_text(line) and bool(VALUE_PATTERNS["percent"].search(line))
        if "REACTIVE POWER" in p:
            return bool(VALUE_PATTERNS["reactive"].search(line))
        if "SHORT CIRCUIT" in p:
            return bool(VALUE_PATTERNS["short_circuit"].search(line))
        if "RESISTANCE" in p:
            return bool(VALUE_PATTERNS["resistance"].search(line))
        if p == "POWER":
            return bool(VALUE_PATTERNS["power"].search(line))
        if "VOLTAGE" in p or p == "SYSTEM":
            return bool(VALUE_PATTERNS["voltage"].search(line))
        return any(pattern.search(line) for name, pattern in VALUE_PATTERNS.items() if name not in {"ct", "vt", "quantity", "oltc", "vector"})

    def _page_has_section_context(self, row: TemplateRow, page: IndexedPage) -> bool:
        section = normalize_text(row.section)
        if not section or section in {"REMOTE END", "OTHER TYPICAL SLD COMPONENTS"}:
            return True
        component = normalize_text(row.component)
        if section == "GIS" and (component.startswith("CT IN ") or component in {"BUS COUPLER", "BUS SECTION"}):
            return True
        phrases = alias_phrases(section)
        if any(phrase in page.normalized for phrase in phrases):
            return True
        # Power-transformer and NGR data are often on the same transformer page.
        if section == "NGR" and "POWER TRANSFORMER" in page.normalized:
            return True
        return False

    def _derive_reference(self, page: IndexedPage, line_idx: int) -> str:
        # Prefer a nearby clause number, then appendix/TMSS/TES identifiers.
        nearby = " | ".join(page.lines[max(0, line_idx - 5): min(len(page.lines), line_idx + 2)])
        clause_matches = CLAUSE_RE.findall(nearby)
        tmss = TMSS_RE.findall(nearby)
        tes = TES_RE.findall(nearby)
        appendix = APPENDIX_RE.search(" | ".join(page.lines[:20]))

        parts = []
        if page.source_kind == "MAIN_SOW":
            parts.append("Main SOW")
        elif page.source_kind == "PROJECT_APPENDIX":
            if appendix and appendix.group(1):
                parts.append(f"Appendix {appendix.group(1)}")
            else:
                parts.append("Project Appendix")
        elif page.source_kind == "DATA_SCHEDULE":
            parts.append("Data Schedule")
        elif page.source_kind == "GENERIC_SPEC":
            parts.append("Generic Specification")

        if clause_matches:
            # Nearby clause closest to the matching text is usually the most useful.
            parts.append(clause_matches[-1])
        for ref in tmss + tes:
            ref = ref.upper()
            if ref not in parts:
                parts.append(ref)
        return " – ".join(parts) if parts else "PTS"

    @staticmethod
    def _reasonable_amp_value(value: str) -> bool:
        m = re.search(r"\d+(?:\.\d+)?", value)
        if not m:
            return False
        try:
            return float(m.group(0)) >= 10.0
        except ValueError:
            return False

    @staticmethod
    def _clean_value(value: str) -> str:
        value = re.sub(r"\s+", " ", value).strip(" |,;:-")
        # Avoid returning an entire paragraph as a drawing value.
        if len(value) > 180:
            value = value[:180].rsplit(" ", 1)[0]
        return value
