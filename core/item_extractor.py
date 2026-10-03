"""
Equipment schedule extraction.

This module converts page text into one record per schedule item instead of
combining every match found on a page into a single row.
"""

import re
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional


@dataclass
class EquipmentRecord:
    source_doc: str = ""
    section_clause: str = ""
    page_number: int = 0
    equipment_item: str = ""
    quantity: str = ""
    rating: str = ""
    standard: str = ""
    notes: str = ""


class EquipmentItemExtractor:
    """Build equipment records from schedule-like PDF text."""

    ITEM_HEADER = re.compile(
        r"^\s*(\d+(?:\.\d+)*[A-Z]?)\s+"
        r"(Each|Set|Sets|Lot|Nos?|No\.|Unit|Units?)\s+"
        r"(\d+(?:\s*\+\s*\d+)?(?:\s*/\s*[A-Za-z]+)?)"
        r"(?:\s+(.*))?$",
        re.IGNORECASE,
    )
    SOURCE = re.compile(
        r"\b(Part\s+[IVX]+|Appendix\s+[IVX]+|Appendix\s+\d+)\b"
        r"(?:\s*[-:]\s*([A-Za-z][A-Za-z0-9 /&-]{2,60}))?",
        re.IGNORECASE,
    )
    CLAUSE = re.compile(r"\b(\d+\.\d+(?:\.\d+)+)\b")
    STANDARD = re.compile(
        r"\b((?:IEC|IEEE|ANSI|ASME|ASTM|ISO|BS|CSA)\s*[\w.-]+)\b",
        re.IGNORECASE,
    )
    STATUS = re.compile(
        r"\b(VERIFIED|PENDING|APPROVED|REVIEW\s+REQUIRED|REJECTED|"
        r"CERTIFIED|TESTED|COMMISSIONED)\b",
        re.IGNORECASE,
    )
    EQUIPMENT = re.compile(
        r"\b(power\s+transformers?|transformers?|circuit\s+breakers?|"
        r"current\s+transformers?|voltage\s+transformers?|"
        r"gis\s+panels?|relay\s+panels?|switchgear|switchboards?|"
        r"disconnect(?:or|ing)?\s+switch(?:es)?|busbars?|bus\s+ducts?|"
        r"cables?|surge\s+arresters?|isolators?|earthing\s+switch(?:es)?|"
        r"grounding\s+switch(?:es)?|capacitors?|reactors?|generators?|"
        r"motors?|batter(?:y|ies)|chargers?|panels?|feeders?|"
        r"protection\s+systems?|control\s+panels?|metering\s+panels?)\b",
        re.IGNORECASE,
    )
    EXPLICIT_QUANTITY_BEFORE = re.compile(
        r"(?:\b(?:one|two|three|four|five|six|seven|eight|nine|ten)"
        r"\s*\(\s*\d+\s*\)|\b\d+(?:\s*\+\s*\d+)?)\s*"
        r"(?:nos?\.?|numbers?|units?|sets?|pcs?)\s*$",
        re.IGNORECASE,
    )

    _IGNORED_LINES = (
        "item # unit qty",
        "drawing control sheet",
        "this document is not",
        "for ordering",
        "construction or",
        "revisions",
        "dept.:",
        "prep. by:",
        "approved",
        "certified",
        "date:",
        "by:",
    )

    def __init__(self) -> None:
        self._current: Optional[EquipmentRecord] = None
        self._description: List[str] = []
        self._last_title = ""
        self._source_doc = ""
        self._section_clause = ""

    def process_page(self, text: str, page_number: int) -> List[Dict[str, str]]:
        """Process one page and return records completed on that page."""
        completed: List[Dict[str, str]] = []
        broad_candidates: List[Dict[str, str]] = []
        if not text:
            return completed

        lines = [self._clean_line(raw_line) for raw_line in text.splitlines()]
        lines = [line for line in lines if line]
        has_schedule_headers = any(self.ITEM_HEADER.match(line) for line in lines)
        preamble: List[str] = []
        for line in lines:
            if not line:
                continue

            self._update_context(line)
            header = self.ITEM_HEADER.match(line)
            if header:
                title_from_description = self._title_from_description()
                inline_title, inline_description = self._split_inline_title(
                    header.group(4) or ""
                )
                if self._current is not None:
                    completed.append(self._finish_record())

                title = (
                    inline_title
                    or title_from_description
                    or self._last_meaningful_line(preamble)
                )
                self._current = EquipmentRecord(
                    source_doc=self._source_doc,
                    section_clause=self._section_clause or header.group(1),
                    page_number=page_number,
                    equipment_item=title,
                    quantity=self._normalise_quantity(header.group(3)),
                )
                self._description = []
                if inline_description:
                    self._description.append(inline_description)
                elif header.group(4):
                    self._description.append(header.group(4))
                preamble = []
                continue

            if self._current is None:
                if self._is_meaningful_title(line):
                    preamble.append(line)
                if not has_schedule_headers:
                    broad_candidates.extend(
                        self._extract_broad_candidates(line, page_number)
                    )
                continue

            if self._is_noise(line):
                continue
            self._description.append(line)
            if not has_schedule_headers:
                broad_candidates.extend(
                    self._extract_broad_candidates(line, page_number)
                )

        if self._current is None and preamble:
            self._last_title = self._last_meaningful_line(preamble)
        elif self._current is not None:
            self._last_title = self._current.equipment_item

        return self._deduplicate_records(completed + broad_candidates)

    def finish(self) -> List[Dict[str, str]]:
        """Finish the final item at the end of the selected page range."""
        if self._current is None:
            return []
        return [self._finish_record()]

    def _finish_record(self) -> Dict[str, str]:
        record = self._current
        description = self._normalise_description(self._description)
        if not self._looks_like_title(record.equipment_item):
            fallback = self._first_description_title()
            if fallback:
                record.equipment_item = fallback
        record.equipment_item = self._normalise_record_title(
            record.equipment_item, description
        )
        record.rating = description
        standards = self.STANDARD.findall(description)
        if standards:
            record.standard = self._join_unique(standards)
        statuses = self.STATUS.findall(description)
        if statuses:
            record.notes = self._join_unique(statuses)
        self._current = None
        self._description = []
        return asdict(record)

    def _title_from_description(self) -> str:
        """Use a short, label-like line immediately before a new item header."""
        for line in reversed(self._description[-8:]):
            if self._looks_like_title(line):
                return line
        return ""

    def _update_context(self, line: str) -> None:
        source_match = self.SOURCE.search(line)
        if source_match:
            source = source_match.group(1).strip()
            detail = (source_match.group(2) or "").strip()
            self._source_doc = f"{source} - {detail}" if detail else source

        clause_match = self.CLAUSE.search(line)
        if clause_match and not self.ITEM_HEADER.match(line):
            self._section_clause = clause_match.group(1)

    @staticmethod
    def _clean_line(line: str) -> str:
        return re.sub(r"\s+", " ", line).strip()

    def _is_meaningful_title(self, line: str) -> bool:
        if self._is_noise(line) or self.ITEM_HEADER.match(line):
            return False
        return self._looks_like_title(line)

    def _looks_like_title(self, line: str) -> bool:
        if len(line) < 4 or len(line) > 80 or self.CLAUSE.fullmatch(line):
            return False
        if line.endswith((".", ",", ";", ":")):
            return False
        if line.lower().startswith(("the ", "one ", "two ", "three ", "each ")):
            return False
        return True

    def _normalise_record_title(self, title: str, description: str) -> str:
        """Prefer a meaningful equipment name over a voltage/spec prefix."""
        title = self._normalise_equipment_name(title)
        if re.fullmatch(
            r"\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?\s*"
            r"(?:kV|kA|A|MW|MVA|Hz)",
            title,
            re.IGNORECASE,
        ):
            matches = self.EQUIPMENT.findall(description)
            if matches:
                return max(
                    (self._normalise_equipment_name(match) for match in matches),
                    key=len,
                )
        return title

    def _is_noise(self, line: str) -> bool:
        lowered = line.lower()
        if any(lowered.startswith(prefix) for prefix in self._IGNORED_LINES):
            return True
        if any(
            marker in lowered
            for marker in (
                "national grid sa",
                "drawing control sheet",
                "sow / ts for power supply",
                "job order no.",
                "page no.",
            )
        ):
            return True
        if re.fullmatch(r"[A-Z0-9 .:/-]{1,8}", line) and len(line) <= 5:
            return True
        return bool(re.fullmatch(r"\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}", line))

    def _extract_broad_candidates(
        self, line: str, page_number: int
    ) -> List[Dict[str, str]]:
        """Extract equipment mentions that are not part of an item header."""
        if self._is_noise(line) or len(line) < 12 or len(line) > 180:
            return []
        if re.search(
            r"\b(contents?|definitions?|abbreviations?|table of contents|"
            r"shall mean|means the|refer to|see appendix|"
            r"requirements?|specification|following|as per|"
            r"contractor|designed|supplied|installed)\b",
            line,
            re.IGNORECASE,
        ):
            return []

        candidates: List[Dict[str, str]] = []
        for match in self.EQUIPMENT.finditer(line):
            equipment = self._normalise_equipment_name(match.group(0))
            if not equipment:
                continue

            before = line[max(0, match.start() - 55):match.start()]
            quantity_match = self.EXPLICIT_QUANTITY_BEFORE.search(before)
            if not quantity_match:
                continue
            quantity = re.sub(r"\s+", "", quantity_match.group(0))
            quantity = re.sub(
                r"(?:nos?\.?|numbers?|units?|sets?|pcs?)$",
                "",
                quantity,
                flags=re.IGNORECASE,
            )
            if "(" in quantity:
                quantity = re.search(r"\d+", quantity).group(0)

            standard_values = self.STANDARD.findall(line)
            status_values = self.STATUS.findall(line)
            candidates.append(
                asdict(
                    EquipmentRecord(
                        source_doc=self._source_doc,
                        section_clause=self._section_clause,
                        page_number=page_number,
                        equipment_item=equipment,
                        quantity=self._normalise_quantity(quantity),
                        rating=self._normalise_description([line]),
                        standard=self._join_unique(standard_values),
                        notes=self._join_unique(status_values),
                    )
                )
            )
        return candidates

    @staticmethod
    def _normalise_equipment_name(value: str) -> str:
        value = re.sub(r"\s+", " ", value).strip(" .,;:-")
        if len(value) < 4:
            return ""
        return value[:1].upper() + value[1:]

    @staticmethod
    def _deduplicate_records(
        records: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        unique: List[Dict[str, str]] = []
        seen = set()
        for record in records:
            key = (
                record.get("page_number"),
                record.get("equipment_item", "").lower(),
                record.get("quantity", ""),
                record.get("rating", "")[:120].lower(),
            )
            if key not in seen and record.get("equipment_item"):
                seen.add(key)
                unique.append(record)
        return unique

    @staticmethod
    def _last_meaningful_line(lines: List[str]) -> str:
        for line in reversed(lines):
            if len(line) >= 4:
                return line
        return ""

    @staticmethod
    def _normalise_quantity(value: str) -> str:
        return re.sub(r"\s+", "", value)

    @staticmethod
    def _split_inline_title(value: str) -> tuple[str, str]:
        value = value.strip()
        value_without_each = re.sub(r"^Each\s+", "", value, flags=re.I)
        value_without_each = re.sub(r"^-\s*The\s+", "", value_without_each, flags=re.I)
        split_pattern = (
            r"(.+?)(?:,\s+|\s+(?:which\s+shall|shall\s+consist|"
            r"consists(?:\s+of)?|includes|is|designed|complying|"
            r"shall\s+be|for\s+the)\b)(.*)"
        )
        match = re.match(split_pattern, value_without_each, re.I)
        if match:
            title = match.group(1).strip(" :-")
            if not title.lower().startswith(("the ", "one ", "two ", "three ")):
                remainder = match.group(2).strip()
                return title, remainder

        if value_without_each and not value_without_each.lower().startswith(
            ("the ", "one ", "two ", "three ")
        ):
            return value_without_each.strip(" :-"), value
        return "", value

    def _first_description_title(self) -> str:
        for line in self._description:
            if self._looks_like_title(line):
                return line
        return ""

    @staticmethod
    def _normalise_description(lines: List[str]) -> str:
        text = " ".join(lines)
        text = re.sub(r"\s+([,.;:])", r"\1", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _join_unique(values: List[str]) -> str:
        result: List[str] = []
        for value in values:
            value = value.strip()
            if value and value.lower() not in {item.lower() for item in result}:
                result.append(value)
        return "; ".join(result)
