"""Left/right GIS bay schedule from AI-validated quantities + remote-end headings.

This is a *user-defined layout rule*; never claim side assignments come from PTS.
Connection wiring is not approved or attempted here.
"""
from __future__ import annotations


def _balanced_counts(total: int) -> tuple[int,int]:
    if not isinstance(total,int) or total<0:raise ValueError('Bay quantity must be >= 0')
    return ((total+1)//2, total//2)


def build_bay_layout(*,ohl_count: int|None, non_ohl_count: int|None,
                     future_count: int|None, outgoing_count: int|None,
                     remote_ends: list[dict]|None = None) -> dict:
    """Place B.1 OHL on LEFT and B.2 OHL on RIGHT, with balanced counts.

    We never assert a remote end's feeder count unless a separate extraction
    verifies it. With two named ends, the order→side mapping is an explicit
    user rule; quantity allocation is NOT stated in the remote-end section.
    """
    ends=sorted(remote_ends or [],key=lambda x:x.get('section_order',9999))
    items=[]
    issues=[]
    breakdown={}
    for kind,total,component in [
        ('OHL',ohl_count,'INCOMER'),
        ('CABLE_AND_EQUIPPED_SPARE',non_ohl_count,'INCOMER'),
        ('FUTURE',future_count,'F-INCOMER'),
        ('TRANSFORMER_OUTGOING',outgoing_count,'OUTGOING'),
    ]:
        if total is None:
            breakdown[kind]={'total':None,'left':None,'right':None}
            issues.append(f'{kind} count unresolved; cannot finish placement')
            continue
        left,right=_balanced_counts(total)
        breakdown[kind]={'total':total,'left':left,'right':right}
        if left != right:
            issues.append(f'{kind}: odd quantity {total}; LEFT {left}, RIGHT {right} (cannot be equal without a dummy bay).')
        for side,count in [('LEFT',left),('RIGHT',right)]:
            for seq in range(1,count+1):
                remote=None
                if kind=='OHL' and len(ends)==2:
                    remote=ends[0] if side=='LEFT' else ends[1]
                items.append({'component':component,'bay_type':kind,'side':side,
                              'side_sequence':seq,'remote_end':remote['name'] if remote else None,
                              'remote_end_pdf_page':remote['pdf_page'] if remote else None,
                              'assignment_source':'USER_LAYOUT_RULE' if kind=='OHL' else 'BALANCED_LAYOUT_RULE'})
    if ohl_count is not None and len(ends)!=2:
        issues.append(f'Found {len(ends)} remote ends; name→side assignment requires review (exactly 2 supported).')
    return {'schema_version':1,'policy':'BALANCE_EACH_BAY_CATEGORY_LEFT_RIGHT',
            'group_order':'REMOTE_END_SECTION_ORDER',
            'remote_end_side_assignment':'B.1 LEFT, B.2 RIGHT (user rule; not proof of circuit designation)',
            'source_ohl_remote_end_quantities_verified':False,
            'remote_ends':ends,'distribution':breakdown,'bays':items,
            'total_on_left':sum(v['left'] for v in breakdown.values() if v['left'] is not None),
            'total_on_right':sum(v['right'] for v in breakdown.values() if v['right'] is not None),
            'issues':issues}


def refresh_bay_layout(plan: dict) -> dict:
    """Rebuild the balanced bay list after engineer edits quantities in the GUI."""
    old=plan.get('bay_layout',{})
    breakdown=old.get('distribution',{})
    def total(key):return breakdown.get(key,{}).get('total')
    ohl=total('OHL')
    non_ohl=total('CABLE_AND_EQUIPPED_SPARE')
    all_incomers=plan['components']['INCOMER']['quantity']
    if all_incomers is not None:
        if ohl is not None and non_ohl is None and all_incomers >= ohl:
            non_ohl = all_incomers - ohl
        elif non_ohl is not None and ohl is None and all_incomers >= non_ohl:
            ohl = all_incomers - non_ohl
        elif ohl is None or non_ohl is None or ohl + non_ohl != all_incomers:
            # Do not pretend a manually entered total proves how many are OHL.
            ohl = None
            non_ohl = all_incomers
    new=build_bay_layout(ohl_count=ohl,non_ohl_count=non_ohl,
        future_count=plan['components']['F-INCOMER']['quantity'],
        outgoing_count=plan['components']['OUTGOING']['quantity'],
        remote_ends=old.get('remote_ends',[]))
    if ohl is None and all_incomers is not None:
        new['issues'].append('Manual total INCOMER lacks verified OHL breakdown; all are drawn as unclassified incomers.')
    plan['bay_layout']=new
    from cad.geometry import create_balanced_placements
    plan['draft_placements']=create_balanced_placements(plan['components'],new)
    return plan
