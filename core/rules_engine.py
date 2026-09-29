"""
Rules Engine Module
Contains data extraction rules using regex patterns and string matching
Designed to be easily extensible for new data types
"""

import re
import logging
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import config

logger = logging.getLogger(__name__)

class ConfidenceLevel(Enum):
    """Confidence levels for extracted data"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

@dataclass
class ExtractedData:
    """Data class for extracted information"""
    field_name: str
    value: str
    page_number: int
    confidence: float
    context: str = ""  # Surrounding text for verification
    extraction_method: str = "regex"  # regex, proximity, etc.

class RulesEngine:
    """
    Engine for applying extraction rules to text content
    Uses regex patterns and contextual analysis
    """

    def __init__(self):
        """Initialize the rules engine with patterns from config"""
        self.patterns = config.EXTRACTION_PATTERNS
        self.compiled_patterns = self._compile_patterns()
        logger.info("RulesEngine initialized with %d pattern categories", len(self.patterns))

    def _compile_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Pre-compile regex patterns for performance"""
        compiled = {}
        for field_name, pattern_list in self.patterns.items():
            compiled[field_name] = [
                re.compile(pattern, re.IGNORECASE | re.MULTILINE)
                for pattern in pattern_list
            ]
        return compiled

    def extract_all_fields(self, text: str, page_number: int) -> List[ExtractedData]:
        """
        Extract all applicable fields from text on a given page

        Args:
            text (str): Text content to search
            page_number (int): Page number where text was found

        Returns:
            List[ExtractedData]: List of extracted data points
        """
        if not text or not text.strip():
            return []

        extracted = []

        # Extract each field type
        for field_name, patterns in self.compiled_patterns.items():
            field_extractions = self._extract_field(text, field_name, patterns, page_number)
            extracted.extend(field_extractions)

        # Post-process to remove duplicates and low-confidence extractions
        extracted = self._post_process_extractions(extracted, text)

        logger.debug(f"Page {page_number}: Extracted {len(extracted)} data points")
        return extracted

    def _extract_field(self, text: str, field_name: str, patterns: List[re.Pattern],
                      page_number: int) -> List[ExtractedData]:
        """
        Extract a specific field type using its patterns

        Args:
            text (str): Text to search
            field_name (str): Name of the field to extract
            patterns (List[re.Pattern]): Compiled regex patterns for this field
            page_number (int): Page number

        Returns:
            List[ExtractedData]: Extracted data for this field
        """
        extractions = []

        for pattern_idx, pattern in enumerate(patterns):
            matches = pattern.finditer(text)

            for match in matches:
                # Get the matched value (usually group 1 if exists, else group 0)
                if match.lastindex and match.lastindex >= 1:
                    value = match.group(1).strip()
                else:
                    value = match.group(0).strip()

                # Skip empty values
                if not value:
                    continue

                # Calculate confidence score
                confidence = self._calculate_confidence(
                    field_name, value, match, text, pattern_idx
                )

                # Get surrounding context
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end].replace('\n', ' ').strip()

                extraction = ExtractedData(
                    field_name=field_name,
                    value=value,
                    page_number=page_number,
                    confidence=confidence,
                    context=context,
                    extraction_method=f"regex_pattern_{pattern_idx}"
                )

                extractions.append(extraction)

        return extractions

    def _calculate_confidence(self, field_name: str, value: str, match: re.Match,
                            text: str, pattern_index: int) -> float:
        """
        Calculate confidence score for an extraction

        Args:
            field_name (str): Name of the field
            value (str): Extracted value
            match (re.Match): Regex match object
            text (str): Full text being searched
            pattern_index (int): Index of the pattern that matched

        Returns:
            float: Confidence score between 0.0 and 1.0
        """
        score = 0.0

        # Base score from pattern specificity (earlier patterns are usually more specific)
        pattern_score = max(0.3, 1.0 - (pattern_index * 0.1))
        score += pattern_score * config.CONFIDENCE_WEIGHTS["regex_match"]

        # Value length score (not too short, not too long)
        value_len = len(value)
        if 3 <= value_len <= 100:
            length_score = 1.0
        elif value_len < 3:
            length_score = 0.3
        else:  # value_len > 100
            length_score = max(0.3, 1.0 - ((value_len - 100) / 200))
        score += length_score * config.CONFIDENCE_WEIGHTS["length_score"]

        # Context score - check for relevant keywords near the match
        context_score = self._calculate_context_score(field_name, match, text)
        score += context_score * config.CONFIDENCE_WEIGHTS["context_score"]

        # Keyword proximity bonus
        proximity_score = self._calculate_proximity_score(field_name, match, text)
        score += proximity_score * config.CONFIDENCE_WEIGHTS["keyword_proximity"]

        # Normalize to 0-1 range
        final_score = min(1.0, max(0.0, score))

        return round(final_score, 3)

    def _calculate_context_score(self, field_name: str, match: re.Match, text: str) -> float:
        """
        Calculate confidence based on contextual keywords

        Args:
            field_name (str): Name of the field
            match (re.Match): Regex match object
            text (str): Full text

        Returns:
            float: Context score (0.0-1.0)
        """
        # Define contextual keywords for each field type
        context_keywords = {
            "equipment_id": ["equipment", "eq.", "tag", "number", "id", "identifier"],
            "rating": ["rating", "spec", "specification", "capacity", "voltage", "current", "power"],
            "quantity": ["quantity", "qty", "q.", "count", "number", "units", "pcs"],
            "standard": ["standard", "ref", "reference", "std", "iec", "ieee", "ansi", "asme"],
            "source_doc": ["source", "doc", "document", "drawing", "part", "section"],
            "notes": ["note", "status", "remark", "comment", "verified", "pending", "approved"]
        }

        keywords = context_keywords.get(field_name, [])
        if not keywords:
            return 0.5  # Neutral score if no context keywords defined

        # Check text around the match
        start = max(0, match.start() - 100)
        end = min(len(text), match.end() + 100)
        context_window = text[start:end].lower()

        # Count how many keywords appear in context
        keyword_count = sum(1 for keyword in keywords if keyword in context_window)
        keyword_ratio = min(1.0, keyword_count / max(len(keywords), 1))

        return keyword_ratio

    def _calculate_proximity_score(self, field_name: str, match: re.Match, text: str) -> float:
        """
        Calculate score based on proximity to field labels

        Args:
            field_name (str): Name of the field
            match (re.Match): Regex match object
            text (str): Full text

        Returns:
            float: Proximity score (0.0-1.0)
        """
        # Define field labels that typically precede the values
        field_labels = {
            "equipment_id": ["equipment id", "eq. id", "tag number", "tag no", "equipment"],
            "rating": ["rating:", "spec:", "specification:", "capacity:", "voltage:", "current:"],
            "quantity": ["quantity:", "qty:", "q.:", "count:", "number:"],
            "standard": ["standard:", "ref:", "reference:", "std:", "iec:", "ieee:"],
            "source_doc": ["source:", "doc:", "document:", "drawing:", "part:", "section:"],
            "notes": ["notes:", "note:", "status:", "remarks:", "comments:"]
        }

        labels = field_labels.get(field_name, [])
        if not labels:
            return 0.5

        # Look for labels before the match
        lookbehind_start = max(0, match.start() - 50)
        lookbehind_text = text[lookbehind_start:match.start()].lower()

        # Check if any label appears close before the match
        for label in labels:
            if label in lookbehind_text:
                # Calculate proximity - closer is better
                label_pos = lookbehind_text.rfind(label)
                distance = len(lookbehind_text) - label_pos - len(label)
                proximity_score = max(0.0, 1.0 - (distance / 30))  # 30 chars max proximity
                return proximity_score

        return 0.2  # Low score if no label found nearby

    def _post_process_extractions(self, extractions: List[ExtractedData],
                                full_text: str) -> List[ExtractedData]:
        """
        Post-process extractions to remove duplicates and filter by confidence

        Args:
            extractions (List[ExtractedData]): Raw extractions
            full_text (str): Full text being processed

        Returns:
            List[ExtractedData]: Filtered and deduplicated extractions
        """
        if not extractions:
            return []

        # Filter by minimum confidence threshold
        filtered = [
            ext for ext in extractions
            if ext.confidence >= config.MIN_CONFIDENCE_THRESHOLD
        ]

        # Group by field_name and page_number to handle duplicates
        grouped = {}
        for ext in filtered:
            key = (ext.field_name, ext.page_number)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(ext)

        # For each group, keep the highest confidence extraction
        deduplicated = []
        for key, extractions_list in grouped.items():
            if len(extractions_list) == 1:
                deduplicated.append(extractions_list[0])
            else:
                # Keep the one with highest confidence
                best = max(extractions_list, key=lambda x: x.confidence)
                deduplicated.append(best)

        # Sort by page number, then by confidence (descending)
        deduplicated.sort(key=lambda x: (x.page_number, -x.confidence))

        logger.debug(f"Post-processing: {len(extractions)} -> {len(filtered)} -> {len(deduplicated)} extractions")
        return deduplicated

    def extract_with_custom_pattern(self, text: str, pattern: str,
                                  field_name: str, page_number: int) -> List[ExtractedData]:
        """
        Extract data using a custom regex pattern (for dynamic rule addition)

        Args:
            text (str): Text to search
            pattern (str): Regex pattern to use
            field_name (str): Name for the extracted field
            page_number (int): Page number

        Returns:
            List[ExtractedData]: Extracted data points
        """
        try:
            compiled_pattern = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
            return self._extract_field(text, field_name, [compiled_pattern], page_number)
        except re.error as e:
            logger.error(f"Invalid regex pattern '{pattern}': {e}")
            return []

    def get_field_statistics(self, extractions: List[ExtractedData]) -> Dict[str, Any]:
        """
        Generate statistics about extracted fields

        Args:
            extractions (List[ExtractedData]): List of extracted data

        Returns:
            Dict[str, Any]: Statistics dictionary
        """
        stats = {
            "total_extractions": len(extractions),
            "by_field": {},
            "by_confidence": {"high": 0, "medium": 0, "low": 0},
            "by_page": {},
            "average_confidence": 0.0
        }

        if not extractions:
            return stats

        # Count by field
        for ext in extractions:
            field = ext.field_name
            if field not in stats["by_field"]:
                stats["by_field"][field] = {"count": 0, "pages": set()}
            stats["by_field"][field]["count"] += 1
            stats["by_field"][field]["pages"].add(ext.page_number)

            # Count by confidence level
            if ext.confidence >= 0.8:
                stats["by_confidence"]["high"] += 1
            elif ext.confidence >= 0.5:
                stats["by_confidence"]["medium"] += 1
            else:
                stats["by_confidence"]["low"] += 1

            # Count by page
            page = ext.page_number
            if page not in stats["by_page"]:
                stats["by_page"][page] = 0
            stats["by_page"][page] += 1

        # Calculate average confidence
        stats["average_confidence"] = sum(ext.confidence for ext in extractions) / len(extractions)

        # Convert sets to lists for JSON serialization
        for field_data in stats["by_field"].values():
            field_data["pages"] = sorted(list(field_data["pages"]))

        return stats

# Convenience functions for easy usage
def extract_data_from_text(text: str, page_number: int) -> List[ExtractedData]:
    """
    Convenience function to extract data from text

    Args:
        text (str): Text content to process
        page_number (int): Page number

    Returns:
        List[ExtractedData]: Extracted data points
    """
    engine = RulesEngine()
    return engine.extract_all_fields(text, page_number)

def extract_data_from_pdf_page(page_text: str, page_number: int) -> List[ExtractedData]:
    """
    Convenience function to extract data from a PDF page

    Args:
        page_text (str): Text from PDF page
        page_number (int): Page number (1-based)

    Returns:
        List[ExtractedData]: Extracted data points
    """
    return extract_data_from_text(page_text, page_number)