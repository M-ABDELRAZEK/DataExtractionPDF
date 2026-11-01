"""Find source-substation remote ends in saved, page-tagged Markdown text.

This module reads specification *headings*, never infers electrical bay quantities.
Remote-end counts per side are user layout rules, not cited design quantities.
"""
from __future__ import annotations
import re

SECTION_START = re.compile(r'\b(?:B\s*[.:-]?\s*)?Source\s+Substation\s*\(\s*Remote\s+Ends\s*\)', re.I)
NEXT_MAIN_SECTION = re.compile(r'^\s*\d{1,2}[.]\d{2}(?:\s+[A-Z].*)?$',re.I)
REMOTE_INDEX = re.compile(r'^\s*B\s*[.:-]\s*(\d+)\s*$', re.I)
REMOTE_INLINE = re.compile(r'^\s*B\s*[.:-]\s*(\d+)\s+(.+)$', re.I)
REMOTE_NUMBER = re.compile(r'\bRemote\s*End\s*#?\s*(\d+)\b', re.I)


def _extract_name(heading: str) -> str:
    # Explicit source-heading name is before "Source Substation" and may be
    # wrapped in the PDF's typographic quote marks.
    text=re.sub(r'\bSource\s+Substation\b.*$', '', heading, flags=re.I)
    text=re.sub(r'^\s*[“”\"‘’\']+|[“”\"‘’\']+\s*$', '',text).strip(' \t:–-')
    return ' '.join(text.split())


def discover_remote_ends(page_texts: dict[int,str]) -> dict:
    """Return ordered remote ends with physical PDF evidence, or an empty list.

    Only scans inside the *first* explicit Source Substation (Remote Ends)
    section, stopping at the following major numbered specification section.
    Handles the two-line `B.1` / `"NAME" Source Substation...` PDF layout.
    """
    active=False
    ends=[]
    seen=set()
    section_pages=[]
    for page in sorted(page_texts):
        raw=page_texts[page]
        lines=[line.strip() for line in raw.splitlines() if line.strip() and not line.strip().startswith('<!--') and not line.strip().startswith('## Physical PDF')]
        if not active:
            matches=[i for i,line in enumerate(lines) if SECTION_START.search(line)]
            if not matches: continue
            active=True
            lines=lines[matches[0]+1:]
        section_pages.append(page)
        for i,line in enumerate(lines):
            if NEXT_MAIN_SECTION.match(line) and not re.match(r'^\s*B\s*[.:-]',line,re.I):
                return {'section':'Source Substation (Remote Ends)',
                        'page_numbers':section_pages,'remote_ends':ends,
                        'quantity_source':'NONE; names/order only'}
            match=REMOTE_INDEX.match(line) or REMOTE_INLINE.match(line)
            if not match: continue
            index=int(match.group(1))
            # Headings may be on one line or the name on the following line.
            snippet=(' '.join(([match.group(2)] if match.lastindex==2 else []) + lines[i+1:i+4])).strip()
            number=REMOTE_NUMBER.search(snippet)
            if not number or index in seen:continue
            name=_extract_name(snippet[:number.start()])
            if not name:continue
            seen.add(index)
            ends.append({'section_order':index,'remote_end_number':int(number.group(1)),
                         'name':name,'pdf_page':page,
                         'heading':f'B.{index} {name} — Remote End #{number.group(1)}'})
    ends.sort(key=lambda r:r['section_order'])
    return {'section':'Source Substation (Remote Ends)',
            'page_numbers':section_pages,'remote_ends':ends,
            'quantity_source':'NONE; names/order only'}
