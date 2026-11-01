"""Machine-readable SLD form contract. The original XLSX is only a layout asset.

The actual supplied workbook has A/B/C as fixed input labels, D/E/F as filled
output, and G for the user's manual notes. Never send XLSX to an LLM.
"""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import hashlib
import json

from core.sld_template_extractor import SLDTemplate


def build_template_json(template_file: str | Path, output_file: str | Path) -> dict:
    template_file = Path(template_file)
    result = {
        'schema_version': 3,
        'source_template_sha256': hashlib.sha256(template_file.read_bytes()).hexdigest(),
        'worksheet': 'SLD',
        'fixed_columns': {'A': 'Section', 'B': 'Component', 'C': 'Parameter'},
        'output_columns': {'D': 'Drawing Value', 'E': 'PTS PDF Page', 'F': 'PTS Reference'},
        'manual_only_columns': {'G': 'Note'},
        'rows': [{
            'id': row.excel_row,
            'section': row.section,
            'component': row.component,
            'parameter': row.parameter,
        } for row in SLDTemplate(template_file).load_rows()],
    }
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    return result


def read_template_json(path: str | Path) -> dict:
    contract = json.loads(Path(path).read_text(encoding='utf-8'))
    if contract.get('schema_version') != 3:
        raise ValueError('Unsupported template JSON schema version')
    rows = contract.get('rows', [])
    if len(rows) != len({int(item['id']) for item in rows}):
        raise ValueError('Duplicate Excel row numbers in template JSON')
    return contract
