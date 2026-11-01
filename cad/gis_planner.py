"""GIS component BOM + named connection metadata from extraction, not guesses.

This is deliberately a REVIEWABLE PLAN, not an approved electrical topology.
CAD drawing on Windows uses actual supplied DWGs as insertable library members.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
import json
import re
from openpyxl import load_workbook

SUPPORTED = {
    'BUSBAR': 'BUSBAR.dwg',
    'BUSSECTION': 'BUSSECTION.dwg',
    'BUSCOUPLER': 'BUSCOUPLER.dwg',
    'INCOMER': 'INCOMER.dwg',
    'F-INCOMER': 'F-INCOMER.dwg',
    'OUTGOING': 'OUTGOING.dwg',
}


def parse_int(value: str | int | None) -> int | None:
    if isinstance(value,int): return value if 0 <= value <= 1000 else None
    string = str(value or '').strip()
    if not string or string.upper() in ('NA','N/A','NONE','—','-'): return None
    # Accept one literal quantity with optional unit or word descriptor (e.g. '4 bays', '4 Nos.', '4 (four)')
    m = re.fullmatch(r'(\d+)(?:\.0+)?(?:\s*\([a-zA-Z]+\))?(?:\s*(?:bays?|nos?\.?|units?|sets?|feeders?|each|ea\.?))?', string, re.I)
    if m:
        n = int(m.group(1))
        return n if n <= 1000 else None
    return None


@dataclass
class GeometryPoint:
    name: str
    x: float
    y: float


def read_vertices(vertices_file: str | Path) -> dict[str,dict[str,dict[str,GeometryPoint]]]:
    wb = load_workbook(vertices_file, read_only=True, data_only=True)
    ws = wb.active
    vendor = ''
    component = ''
    found = defaultdict(lambda: defaultdict(dict))
    for row in ws.iter_rows(min_row=3, values_only=True):
        first, second, name, x, y = (list(row[:5]) + [None]*5)[:5]
        if first: vendor = str(first).strip().upper()
        if second: component = str(second).strip().upper()
        if not (vendor and component and name): continue
        if not isinstance(x, (int,float)) or not isinstance(y, (int,float)):
            raise ValueError(f'Invalid vertex coords for {vendor}/{component}/{name}')
        found[vendor][component][str(name).strip().upper()] = GeometryPoint(str(name).strip(), float(x), float(y))
    wb.close()
    return {k: {name: points for name, points in v.items()} for k,v in found.items()}


def gis_quantities(excel_path: str | Path) -> tuple[dict[str, int | None],dict]:
    wb = load_workbook(excel_path, read_only=True, data_only=True)
    ws = wb['SLD']
    section, component = '', ''
    bays = {}
    for row in ws.iter_rows(min_row=3, max_col=4, values_only=True):
        sec, comp, param, val = row
        if sec: section=str(sec).strip()
        if comp: component=str(comp).strip()
        if section.casefold() != 'gis' or component.casefold() != 'bays':
            continue
        if not param: continue
        bays[str(param).strip().casefold()] = parse_int(val)
    wb.close()
    def pick(key): return bays.get(key.casefold())
    line = [pick('OHL Feeder'),pick('Cable Feeder')]
    # Do not double-count spare bays in current incomers; spare equipped
    # may be a separately numbered feeder or already part of project totals.
    active = sum(line) if all(v is not None for v in line) else None
    numbers = {
        'INCOMER': active,
        'F-INCOMER': pick('Future'),
        'OUTGOING': pick('Transformer Feeder'),
        'BUSCOUPLER': pick('Bus Coupler'),
        'BUSSECTION': pick('Bus Section'),
        # A double busbar arrangement does NOT determine drawing module
        # counts. Set to None until the rail-layout spec is confirmed.
        'BUSBAR': None,
    }
    # Use exact source schedule quantities where available (more reliable than
    # the legacy general-purpose regex).
    schedule_path = Path(excel_path).with_name('gis_schedule_regex.json')
    schedule = {}
    if schedule_path.exists():
        try: schedule = json.loads(schedule_path.read_text(encoding='utf-8')).get('values',{})
        except (OSError,ValueError): pass
    def scheduled(key): return schedule.get(key,{}).get('main')
    if scheduled('OHL_FEEDER') is not None and scheduled('CABLE_FEEDER') is not None:
        # Cable-feeder spare is an equipped spare, unlike future unequipped bay.
        numbers['INCOMER'] = (scheduled('OHL_FEEDER') + scheduled('CABLE_FEEDER')
            + schedule['CABLE_FEEDER'].get('spare',0))
    if scheduled('TRANSFORMER_FEEDER') is not None:
        numbers['OUTGOING'] = scheduled('TRANSFORMER_FEEDER')
    if scheduled('BUSCOUPLER') is not None:
        numbers['BUSCOUPLER'] = scheduled('BUSCOUPLER')
    if scheduled('BUSSECTION_WITH_CB') is not None and scheduled('BUSSECTION_WITHOUT_CB') is not None:
        numbers['BUSSECTION'] = scheduled('BUSSECTION_WITH_CB') + scheduled('BUSSECTION_WITHOUT_CB')
    # Future bays are not necessarily the same as equipped spares. The legacy
    # value is unverified unless backed by an explicit future-bay schedule.
    numbers['F-INCOMER'] = None
    return numbers, {'original_bays': bays, 'schedule_evidence':schedule, 'spare_equipped': pick('Spare Equipped'),
                     'warnings':['Cable feeder spare is counted as an equipped INCOMER; confirm against SLD topology before approving.',
                                 'Future incomer quantity is unverified and must be approved separately.',
                                 'BUSBAR module count must be confirmed from actual GIS drawing geometry.']}


def build_cad_plan(excel_path: str | Path, vertices_path: str | Path,
                   vendor_dir: str | Path, out_json: str | Path,
                   vendor: str = 'HYUNDAI') -> dict:
    vendor = vendor.strip().upper()
    point_map = read_vertices(vertices_path)
    counts, details = gis_quantities(excel_path)
    files = {name: str((Path(vendor_dir)/filename).resolve()) for name, filename in SUPPORTED.items()}
    components = {}
    issues = details['warnings'][:]
    for name, qty in counts.items():
        points = point_map.get(vendor, {}).get(name, {})
        path = Path(files[name])
        if not path.is_file(): issues.append(f'Missing library DWG: {path}')
        if not points: issues.append(f'Missing vertices for {vendor}/{name}')
        if qty is None: issues.append(f'Unresolved quantity for {name}')
        components[name] = {'quantity': qty, 'dwg': str(path),
                           'vertices': {label: asdict(point) for label,point in points.items()}}
    result = {'schema_version': 1, 'vendor': vendor, 'source_excel': str(Path(excel_path).resolve()),
              'template_review_required': True, 'geometry_status': 'DRAFT_NOT_ROUTED',
              'components': components, 'evidence':details, 'issues':issues}
    output = Path(out_json); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    return result


def _interpreted_quantity(value) -> tuple[int | None, bool]:
    """Parse an AI-returned quantity; never search the source specification for values.

    A feeder answer of '2 Main + 1 Spare Equipped' represents THREE bays.
    Returns (total, spare_already_included). Ambiguous text stays unresolved.
    """
    number=parse_int(value)
    if number is not None:return number,False
    if value is None:return None,False
    text=str(value).strip()
    # Only use explicit values with a separate spare term; the LLM is asked
    # to distinguish normal, equipped-spare and future bays in its answer.
    match=re.fullmatch(r'\s*(\d+)\s*(?:main|active|existing|feeders?|bays?)?\s*\+\s*(\d+)\s*(?:(?:equipped\s+)?spares?|spares?\s+equipped)(?:\s+(?:bay|bays))?\s*',text,re.I)
    if match:return int(match[1])+int(match[2]), True
    # Some PTS schedules print the quantity as '2 + 1 (inter tie) (spare)'.
    # Still require an explicit SPARE label to interpret the second quantity.
    match=re.fullmatch(r'\s*(\d+)\s*\+\s*(\d+)\s*(?:\(inter\s*tie\)\s*)?\((?:equipped\s+)?spare\)\s*',text,re.I)
    if match:return int(match[1])+int(match[2]), True
    return None,False


def build_cad_plan_from_json(results_json: str | Path, vertices_path: str | Path,
                             vendor_dir: str | Path, out_json: str | Path,
                             vendor: str = 'HYUNDAI',
                             future_bays_override: int | None = None) -> dict:
    """Compute GIS quantities from accepted AI JSON, never regex or older XLSX.

    Future bays may be manually specified by an engineer; this is recorded as
    an override, never misrepresented as extracted project specification data.
    """
    data=json.loads(Path(results_json).read_text(encoding='utf-8'))
    if data.get('schema_version') != 3:raise ValueError('Expected v3 extraction_results.json')
    if future_bays_override is not None and not (0<=future_bays_override<=200):
        raise ValueError('Future bays override must be between 0 and 200')
    bay_rows={}
    for row in data['rows']:
        if row['section'].casefold()=='gis' and row['component'].casefold()=='bays':
            bay_rows[row['parameter'].casefold()]=row
    def read(parameter):
        item=bay_rows.get(parameter.casefold())
        if not item or item.get('status')!='EVIDENCE_QUOTE_MATCHED_REVIEW_REQUIRED':
            return None,False,item
        qty, includes_spare = _interpreted_quantity(item.get('value'))
        return qty, includes_spare, item
    ohl,_,ohl_row=read('OHL Feeder')
    cable,cable_has_spare,cable_row=read('Cable Feeder')
    spare,_,spare_row=read('Spare Equipped')
    outgoing,_,out_row=read('Transformer Feeder')
    coupler,_,coupler_row=read('Bus Coupler')
    section,_,section_row=read('Bus Section')
    future,_,future_row=read('Future')
    notes=[]
    if cable is not None and not cable_has_spare:
        if spare is None:
            # If separate spare quantity isn't proven, do not assert final count.
            notes.append('Cable feeder spare is not included in cable answer; spare qty unavailable. Confirm if spare-equipped bays exist.')
            cable=None
        else:
            cable+=spare
    if cable_has_spare and spare is not None and spare>cable:
        notes.append('Spare quantity conflicts with cable feeder total; manual review required.')
        cable=None
    if future_bays_override is not None:
        future=future_bays_override
        future_source='USER_OVERRIDE'
    elif future is not None:
        future_source='GROQ_EVIDENCE_REQUIRES_REVIEW'
    else:
        future_source='NOT_FOUND_USER_MAY_ADD'
    from cad.bay_layout import build_bay_layout
    source_remote_ends=data.get('remote_ends',{}).get('remote_ends',[])
    bay_layout=build_bay_layout(ohl_count=ohl,non_ohl_count=cable,
        future_count=future,outgoing_count=outgoing,remote_ends=source_remote_ends)
    notes.extend(bay_layout['issues'])
    numbers={
        'INCOMER':ohl+cable if ohl is not None and cable is not None else None,
        'F-INCOMER':future,
        'OUTGOING':outgoing,
        'BUSCOUPLER':coupler,
        'BUSSECTION':section,
        'BUSBAR':2,  # ONE template DWG segment per side; layout decision, NOT extracted PTS quantity
    }
    if section is not None:
        notes.append('BUSSECTION.dwg represents CB-equipped type. If the specification also has a non-CB bus section, split the counts before approval.')
    if numbers['INCOMER'] is not None:
        notes.append('Equipped spare counted as INCOMER, not F-INCOMER; do not double count.')
    if future_source=='NOT_FOUND_USER_MAY_ADD':
        notes.append('Future bay count not established from cited specification text; user may enter any nonnegative amount.')
    notes.append('BUSBAR=2 is one HYUNDAI DWG segment per side, set by layout rule, not a PTS quantity; busbar extent and all electrical connections need review.')
    point_map=read_vertices(vertices_path)
    vendor=vendor.strip().upper()
    components={}
    issues=notes[:]
    vendor_dir=Path(vendor_dir)
    for name, qty in numbers.items():
        path=vendor_dir/SUPPORTED[name]
        pts=point_map.get(vendor,{}).get(name,{})
        if not path.is_file(): issues.append(f'Missing library DWG: {path}')
        if not pts:issues.append(f'Missing connection points for {vendor}/{name}')
        if qty is None:issues.append(f'Unresolved quantity for {name}')
        components[name]={'quantity':qty,'dwg':str(path.resolve()),
            'vertices':{p:asdict(vertex) for p,vertex in pts.items()}}
    evidence={name:({
        'value':row.get('value'),'pages':row.get('pages'),'reference':row.get('reference'),
        'status':row.get('status'),'evidence':row.get('evidence')
    } if row else None) for name,row in {
        'OHL Feeder':ohl_row,'Cable Feeder':cable_row,'Spare Equipped':spare_row,
        'Transformer Feeder':out_row,'Bus Coupler':coupler_row,
        'Bus Section':section_row,'Future':future_row}.items()}
    result={'schema_version':3,'vendor':vendor,
        'source_json':str(Path(results_json).resolve()),
        'bay_layout':bay_layout,
        'future_bays':{'drawing_quantity':future,'source':future_source,
            'manual_override':future_bays_override},
        'geometry_status':'DRAFT_NOT_ROUTED',
        'electrical_topology_approved':False,
        'components':components,'evidence':evidence,'issues':issues}
    from cad.geometry import create_balanced_placements
    if all(component['vertices'] for component in components.values()):
        result['draft_placements']=create_balanced_placements(components,bay_layout)
        result['placement_status']='REMOTE_END_ORDERED_BALANCED_UNCONNECTED'
    else:
        result['draft_placements']=[]
        result['placement_status']='MISSING_VERTICES'
    out_json=Path(out_json)
    out_json.parent.mkdir(parents=True,exist_ok=True)
    out_json.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    return result
