"""Section Markdown -> Groq AI PRIMARY extraction -> audit JSON -> Python XLSX.

NO regexp-based specification values are written to the output workbook.
Regex/text tokenisation is for PDF section detection and evidence retrieval only.
All responses require page-tagged verbatim evidence. Unresolved rows remain NA.
"""
from __future__ import annotations
from dataclasses import asdict
from collections import defaultdict
from pathlib import Path
import hashlib
import json
import logging
import re

from core.groq_extractor import GroqExtractor, GroqAPIError, AIExtraction, DEFAULT_MODEL
from core.markdown_sections import MarkdownSectionizer
from core.remote_ends import discover_remote_ends
from core.markdown_sections import read_markdown_page_segments
from core.sld_template_extractor import (
    SLDTemplate, IndexedPage, PDFIndex, TemplateRow, ExtractionResult,
    normalize_text, meaningful_tokens, tokenise,
)
from core.template_contract import build_template_json

log = logging.getLogger(__name__)


def _retrieve_context(index: PDFIndex, markdown_pages: dict[int,str],
                      rows: list[TemplateRow], *, max_chars: int = 10500) -> tuple[str, list[int]]:
    """Find clauses by section/component/parameter, NOT by regex-extracted values.

    Larger source windows guard against a subject introduced before its rating.
    Adjacent pages are included when budget allows. Every context chunk carries
    a PHYSICAL page header to support independently checked evidence quotes.
    """
    scored_pages: dict[int, tuple[int, int]] = {}
    for row in rows:
        for rank, candidate in enumerate(index.candidate_pages(row, limit=12)):
            score = 12 - rank
            if candidate.source_priority == 0:
                score += 6
            current = scored_pages.get(candidate.page_number, (-1, 0))
            scored_pages[candidate.page_number] = (max(score, current[0]), current[1] + 1)
    # Retrieval diversification: pages relevant to multiple targets get a boost;
    # full source section/page excerpts are preserved in saved Markdown.
    ordered = sorted(scored_pages, key=lambda p: (-scored_pages[p][1], -scored_pages[p][0], p))
    if not ordered:
        return '', []
    tokens = {t.casefold() for r in rows for t in meaningful_tokens(r.section, r.component, r.parameter)}
    # Include engineering aliases for abbreviations in the original template.
    aliases = {'SA': ['surge arrester','surge arrestor'], 'CB':['circuit breaker'],
               'CT':['current transformer'], 'VT':['voltage transformer'],
               'GIB':['gas insulated bus'], 'GIS':['gas insulated switchgear']}
    for row in rows:
        for label in (row.component, row.parameter):
            for key,values in aliases.items():
                if re.search(r'\b'+key+r'\b',label,re.I):
                    tokens.update(w.casefold() for value in values for w in value.split())
    parts=[]
    selected=[]
    used=0
    for number in ordered[:16]:
        text=markdown_pages.get(number,'')
        if not text.strip(): continue
        lines=[s.rstrip() for s in text.splitlines() if not s.lstrip().startswith('<!-- PDF_PAGE:')]
        if not lines: continue
        # A complete short source page is better than regex-like isolated lines.
        # For long pages capture the neighborhoods (up to 25 lines either side)
        # around target terms; include paragraph endings and table line neighbors.
        body='\n'.join(lines)
        remaining=max_chars-used-30
        if remaining<450: break
        if len(body)>remaining:
            matches=[]
            for i,line in enumerate(lines):
                low=line.casefold()
                n=sum(1 for t in tokens if len(t)>2 and re.search(r'\b'+re.escape(t)+r'\b',low))
                if n: matches.append((n,i))
            if matches:
                indices=set()
                for _score,i in sorted(matches,key=lambda item:(-item[0],item[1]))[:7]:
                    indices.update(range(max(0,i-18),min(len(lines),i+31)))
                body='\n'.join(lines[i] for i in sorted(indices))
            body=body[:remaining]
        chunk=f'[PDF PAGE {number}]\n{body}\n'
        parts.append(chunk)
        used+=len(chunk)
        selected.append(number)
        if used>=max_chars:break
    return '\n'.join(parts),selected


def _blank_prediction(reason: str) -> AIExtraction:
    return AIExtraction('NA',[],'NA','',False,reason)


def run_pipeline(pdf_path: str | Path, output_dir: str | Path,
                 template_path: str | Path, *, start_page: int = 1,
                 end_page: int | None = None, use_ai: bool = True,
                 groq_model: str | None = None, groq_api_key: str | None = None,
                 max_ai_rows: int | None = None,
                 progress=None, stop=None, ocr_missing: bool = False) -> dict:
    """Produce full audit/debug assets, one JSON results document, and XLSX.

    AI is mandatory for actual extraction. A no-AI run is allowed strictly to
    inspect the Markdown, template JSON and NA workbooks (not mock up values).
    """
    pdf_path, output_dir, template_path = Path(pdf_path), Path(output_dir), Path(template_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    # Fail fast on invalid key / forbidden model *before* the expensive PDF stage.
    # Do NOT publish a misleading all-NA workbook after a provider error.
    ai=GroqExtractor(model=groq_model or DEFAULT_MODEL, api_key=groq_api_key,
        stop=stop, on_rate_limit=(lambda seconds: progress(.35,
            f'Groq limit reached; waiting {int(seconds)}s for quota reset (Stop to cancel)') if progress else None)) if use_ai else None
    if ai is not None:
        if progress: progress(.01,'Groq connection/permission preflight ...')
        try:
            ai.test_connection()
            (output_dir/'api_connection_error.json').unlink(missing_ok=True)
        except Exception as exc:
            diagnostic=exc.to_safe_dict() if isinstance(exc,GroqAPIError) else {
                'status':'failed','diagnostic':str(exc)[:550]}
            diagnostic['model']=ai.model
            (output_dir/'api_connection_error.json').write_text(
                json.dumps(diagnostic,indent=2,ensure_ascii=False),encoding='utf-8')
            raise RuntimeError('Groq preflight failed; extraction stopped before PDF parsing. '
                               +diagnostic['diagnostic']) from None
    contract_path=output_dir/'template_schema.json'
    contract=build_template_json(template_path,contract_path)
    templates=SLDTemplate(template_path)
    rows=templates.load_rows()
    markdown_dir=output_dir/'intermediate'/'markdown'
    manifest_path=markdown_dir/'manifest.json'
    manifest=None
    if manifest_path.exists():
        try:
            candidate=json.loads(manifest_path.read_text(encoding='utf-8'))
            expected_end=min(end_page or candidate['physical_pages_total'],candidate['physical_pages_total'])
            if (candidate.get('ocr_missing_enabled')==ocr_missing
                and candidate.get('range')==[start_page,expected_end]
                and candidate.get('pdf_sha256')==MarkdownSectionizer._hash_file(pdf_path)
                and all((markdown_dir / r['file']).is_file() for r in candidate['sections'])):
                manifest=candidate
        except (OSError,ValueError,KeyError): pass
    if manifest is None:
        manifest=MarkdownSectionizer().convert(pdf_path,markdown_dir,start_page,end_page,
            ocr_missing=ocr_missing,stop=stop,
            progress=(lambda a,b: progress(.35*a/b,f'Sections {a}/{b}') if progress else None))
    if stop and stop(): raise InterruptedError('Stopped')
    page_texts=read_markdown_page_segments(manifest,markdown_dir)
    remote_ends_info=discover_remote_ends(page_texts)
    remote_ends_json=output_dir/'remote_ends.json'
    remote_ends_json.write_text(json.dumps(remote_ends_info, indent=2, ensure_ascii=False), encoding='utf-8')
    indexed=[]
    for page,text in sorted(page_texts.items()):
        cleaned=re.sub(r'^## Physical PDF page \d+\s*$','',text,flags=re.M)
        lines=cleaned.splitlines()
        indexed.append(IndexedPage(page,cleaned,normalize_text(cleaned),lines,
            [normalize_text(x) for x in lines],[tokenise(x) for x in lines],tokenise(cleaned)))
    PDFIndex._classify_sources(indexed)
    index=PDFIndex(indexed)
    # This is only document metadata, never a model-extracted specification rating.
    project=pdf_path.stem
    groups=defaultdict(list)
    for row in rows: groups[(row.section,row.component)].append(row)
    batches=[]
    for related in groups.values():
        for i in range(0,len(related),5):batches.append(related[i:i+5])
    records={}
    checkpoint_path=output_dir/'extraction_checkpoint.json'
    def save_checkpoint(*, complete: bool = False):
        # Atomic write: failure mid-extraction never destroys the previous batch.
        state={'schema_version':1,'complete':complete,'source_pdf':pdf_path.name,
               'model':groq_model or DEFAULT_MODEL if use_ai else None,
               'completed_rows':len(records),'total_rows':len(rows),
               'rows':[records[key] for key in sorted(records)]}
        tmp=checkpoint_path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
        tmp.replace(checkpoint_path)
    responses_dir=output_dir/'intermediate'/'api_debug'
    responses_dir.mkdir(parents=True,exist_ok=True)
    ai_calls=0
    attempted=0
    for bi,batch in enumerate(batches,1):
        if stop and stop():raise InterruptedError('Stopped')
        budget=max(0,max_ai_rows-attempted) if max_ai_rows is not None else len(batch)
        batch_to_call=batch[:budget]
        context,allowed=_retrieve_context(index,page_texts,batch_to_call) if batch_to_call else ('',[])
        prompts=[{'id':r.excel_row,'section':r.section,'component':r.component,
                  'parameter':r.parameter} for r in batch_to_call]
        answers={}
        error=''
        request_hash=hashlib.sha256(json.dumps({'model':groq_model or DEFAULT_MODEL,
            'targets':prompts,'context':context},sort_keys=True).encode('utf-8')).hexdigest()
        debug_file=responses_dir/f'{request_hash[:18]}.json'
        if ai and context and batch_to_call:
            try:
                if debug_file.is_file():
                    saved=json.loads(debug_file.read_text(encoding='utf-8'))
                    if saved.get('sha256')==request_hash and saved.get('status')=='ok':
                        answers={int(k):AIExtraction(**v) for k,v in saved['answers'].items()}
                if not answers:
                    ai_calls+=1
                    answers=ai.extract_batch(prompts,context,allowed)
                    debug_file.write_text(json.dumps({'sha256':request_hash,'status':'ok',
                        'targets':prompts,'pages':allowed,
                        'context':context,'answers':{str(k):asdict(v) for k,v in answers.items()}},
                        ensure_ascii=False,indent=2),encoding='utf-8')
            except Exception as exc:
                # Provider failures are fatal, not parameter-level missing values.
                # Preserve Markdown already generated for debugging or rerun.
                interrupted=isinstance(exc,InterruptedError)
                detail=exc.to_safe_dict() if isinstance(exc,GroqAPIError) else {
                    'status':'stopped' if interrupted else 'failed','diagnostic':str(exc)[:550]}
                detail.update({'model':ai.model,'batch':bi,'target_ids':[r.excel_row for r in batch_to_call]})
                (output_dir/'api_connection_error.json').write_text(
                    json.dumps(detail,indent=2,ensure_ascii=False),encoding='utf-8')
                log.error('Groq stopped at batch %d: %s',bi,detail['diagnostic'])
                save_checkpoint()
                # Partial outputs are clearly labeled and never masquerade as completed data.
                partial=[]
                for row in rows:
                    partial.append(records.get(row.excel_row, {
                        'id':row.excel_row,'section':row.section,'component':row.component,
                        'parameter':row.parameter,'value':'NA','pages':[],
                        'reference':'NA','evidence':'','status':'PENDING',
                        'reason':'NOT_YET_PROCESSED','source':'none'}))
                (output_dir/'extraction_results_PARTIAL.json').write_text(json.dumps({
                    'complete':False,'error':detail,'source_pdf':pdf_path.name,
                    'model':ai.model,'rows':partial},indent=2,ensure_ascii=False),encoding='utf-8')
                templates.create_output(output_dir/'Extracted Data PARTIAL.xlsx',project,{
                    r['id']:ExtractionResult(r['value'],
                        '; '.join(map(str,r['pages'])) if r['pages'] else 'NA',
                        r['reference']) for r in partial})
                if interrupted:
                    raise InterruptedError('Stopped; extraction checkpoint and PARTIAL Excel preserved') from None
                raise RuntimeError('Groq extraction stopped at batch '
                                   f'{bi}. Markdown/debug files and PARTIAL Excel were preserved. '
                                   +detail['diagnostic']) from None
        attempted+=len(batch_to_call)
        for row in batch:
            if not use_ai: prediction=_blank_prediction('AI_DISABLED_NO_VALUES_EXTRACTED')
            elif row not in batch_to_call: prediction=_blank_prediction('AI_BUDGET_EXHAUSTED')
            elif not context: prediction=_blank_prediction('NO_SOURCE_CONTEXT')
            elif error: prediction=_blank_prediction('API_FAILED: '+error)
            else: prediction=answers.get(row.excel_row,_blank_prediction('API_MISSING_ROW'))
            status='EVIDENCE_QUOTE_MATCHED_REVIEW_REQUIRED' if prediction.verified and prediction.value.upper()!='NA' else 'UNRESOLVED'
            records[row.excel_row]={
                'id':row.excel_row,'section':row.section,'component':row.component,
                'parameter':row.parameter, 'value':prediction.value,
                'pages':prediction.pages,'reference':prediction.reference,
                'evidence':prediction.evidence,'status':status,
                'reason':prediction.reason,'source':'groq_api' if use_ai else 'none',
                'request_hash':request_hash if row in batch_to_call and context else None,
            }
        save_checkpoint()
        if progress:progress(.35+.63*bi/max(1,len(batches)),f'Groq groups {bi}/{len(batches)}')
    save_checkpoint(complete=True)
    ordered=[records[r.excel_row] for r in rows]
    results_json=output_dir/'extraction_results.json'
    results_json.write_text(json.dumps({'schema_version':3,'source_pdf':pdf_path.name,
        'template_sha256':contract['source_template_sha256'],'project':project,
        'model':groq_model or DEFAULT_MODEL if use_ai else None,
        'ai_required_for_values':True,'remote_ends':remote_ends_info,'rows':ordered},indent=2,ensure_ascii=False),encoding='utf-8')
    output_excel=output_dir/'Extracted Data.xlsx'
    to_excel={r['id']:ExtractionResult(r['value'],
        '; '.join(map(str,r['pages'])) if r['pages'] else 'NA',r['reference']) for r in ordered}
    templates.create_output(output_excel,project,to_excel)
    audit_json=output_dir/'extraction_audit.json'
    audit_json.write_text(json.dumps({'ai_primary':True,'rows':ordered},indent=2,ensure_ascii=False),encoding='utf-8')
    if progress:progress(1.0,'Finished')
    return {'output_excel':str(output_excel),'results_json':str(results_json),
        'template_json':str(contract_path),'audit_json':str(audit_json),
        'remote_ends_json':str(remote_ends_json),
        'markdown_manifest':str(manifest_path),'pdf_pages':len(indexed),
        'markdown_sections':len(manifest['sections']),'total_rows':len(rows),
        'found':sum(r['status'].startswith('EVIDENCE') for r in ordered),
        'ai_requested':ai_calls,'unresolved':sum(r['status']=='UNRESOLVED' for r in ordered)}
