"""Affine translation of locally defined vendor connection points.

No rotations, mirroring, scaling or electrical topology are inferred. All
block coordinates use the vendor drawing's 0,0 origin and shared DWG units.
A vendor's anchor can be mapped to an explicit global drawing coordinate.
"""
from __future__ import annotations

ANCHOR_NAMES={
    'BUSBAR':'CONNECTION-FIRSTINCOMER-01',
    'BUSSECTION':'CONNECTION-UPPER-LEFT-01',
    'BUSCOUPLER':'CONNECTION-UPPER-BB-01',
    'INCOMER':'CONNECTION-UPPER-BB-01',
    'F-INCOMER':'CONNECTION-UPPER-BB-01',
    'OUTGOING':'CONNECTION-UPPER-BB-01',
}

def alignment_offset(name: str, vertices: dict, target_x: float, target_y: float) -> dict:
    """Translate a named vertex exactly to its target; return world vertices."""
    key=ANCHOR_NAMES.get(name)
    if not key or key not in vertices:
        raise ValueError(f'Missing CAD anchor point {name}/{key}')
    source=vertices[key]
    tx=target_x-float(source['x'])
    ty=target_y-float(source['y'])
    world={k:{'x':float(v['x'])+tx,'y':float(v['y'])+ty} for k,v in vertices.items()}
    return {'anchor':key,'target':{'x':target_x,'y':target_y},
            'insert':{'x':tx,'y':ty,'z':0.0},'world_vertices':world}


def create_draft_placements(components: dict, *, bay_pitch: float = 130.0,
                            row_pitch: float = 160.0) -> list[dict]:
    """Unconnected inventory grid aligned BY VERTEX rather than raw DWG base point."""
    placements=[]
    order=['BUSBAR','BUSSECTION','BUSCOUPLER','INCOMER','F-INCOMER','OUTGOING']
    for group,name in enumerate(order):
        component=components[name]
        qty=component['quantity']
        if qty is None:continue
        for i in range(qty):
            aligned=alignment_offset(name,component['vertices'],i*bay_pitch,group*row_pitch)
            placements.append({'component':name,'index':i+1,**aligned})
    return placements


def create_balanced_placements(components: dict, bay_layout: dict, *,
                               bay_pitch: float = 130.0, row_pitch: float = 160.0) -> list[dict]:
    """Position GIS elements around a central bus section, NOT an electrical netlist.

    The vendor's LOCAL vertex is mapped into a WORLD drawing point for each
    block. Both busbar segments use their provided 'BS-*' vertices to approach
    the respective bus-section upper endpoints; no wire is added automatically.
    Lower points and clearances still require independent AutoCAD validation.
    """
    placements=[]
    indices={name:0 for name in components}

    def put(name, target_x, target_y, *, anchor_override=None, **extra):
        if name not in components or not components[name].get('vertices'):return
        vertices=components[name]['vertices']
        if anchor_override:
            if anchor_override not in vertices:
                raise ValueError(f'Cannot align {name}: missing {anchor_override}')
            anchor=vertices[anchor_override]
            tx=float(target_x)-float(anchor['x']);ty=float(target_y)-float(anchor['y'])
            aligned={'anchor':anchor_override,'target':{'x':target_x,'y':target_y},
                     'insert':{'x':tx,'y':ty,'z':0.},
                     'world_vertices':{k:{'x':float(v['x'])+tx,'y':float(v['y'])+ty}
                                       for k,v in vertices.items()}}
        else:
            aligned=alignment_offset(name,vertices,float(target_x),float(target_y))
        indices[name]+=1
        placements.append({'component':name,'index':indices[name],**aligned,**extra})

    section=components.get('BUSSECTION',{}).get('quantity') or 0
    if section:
        put('BUSSECTION',0.,0.,bay_type='BUS_SECTION',side='CENTER')
        for extra_section in range(1,section):
            put('BUSSECTION',extra_section*bay_pitch,2.5*row_pitch,
                bay_type='ADDITIONAL_BUS_SECTION_REVIEW',side='UNASSIGNED')

    if (components.get('BUSBAR',{}).get('quantity') or 0)>=2:
        section_vertex=components['BUSSECTION']['vertices']
        upper_left=section_vertex['CONNECTION-UPPER-LEFT-01']
        upper_right=section_vertex['CONNECTION-UPPER-RIGHT-01']
        put('BUSBAR',float(upper_left['x']),float(upper_left['y']),
            anchor_override='CONNECTION-BS-UPPER-RIGHT-01',bay_type='LEFT_BUS_SEGMENT',side='LEFT')
        put('BUSBAR',float(upper_right['x']),float(upper_right['y']),
            anchor_override='CONNECTION-BS-UPPER-LEFT-01',bay_type='RIGHT_BUS_SEGMENT',side='RIGHT')
        for n in range(2,components['BUSBAR']['quantity']):
            put('BUSBAR',n*bay_pitch,3*row_pitch,bay_type='ADDITIONAL_BUSBAR_REVIEW',side='UNASSIGNED')

    # Each side holds an independent column of slots. The columns are symmetric
    # about the central Bus Section; slot ordering is by type and remote section.
    for side in ('LEFT','RIGHT'):
        side_bays=[b for b in bay_layout.get('bays',[]) if b['side']==side]
        for i,bay in enumerate(side_bays,1):
            x=(-1. if side=='LEFT' else 1.)*i*bay_pitch
            put(bay['component'],x,0.,bay_type=bay['bay_type'],side=side,
                remote_end=bay.get('remote_end'),
                allocation_source=bay.get('assignment_source'),slot=i)
    # Couplers do not form part of source-feeder balance. Keep them visible
    # around the Bus Section for engineer placement rather than implying wiring.
    couplers=components.get('BUSCOUPLER',{}).get('quantity') or 0
    for i in range(couplers):
        sign=-1 if i%2==0 else 1
        put('BUSCOUPLER',sign*bay_pitch/2,(1+i//2)*row_pitch,
            bay_type='BUS_COUPLER_REVIEW',side=('LEFT' if sign<0 else 'RIGHT'))

    return placements
