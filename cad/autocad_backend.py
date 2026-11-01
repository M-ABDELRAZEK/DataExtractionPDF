"""AutoCAD COM driver for the UNCONNECTED GIS symbol draft.

This is intentionally NOT an electrically validated/routed SLD.
The driver retries only the transient COM errors AUTO_CAD_BUSY_HRESULTS.
Other exceptions propagate immediately with the failed CAD stage attached.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, TypeVar
import json
import os
import time

T = TypeVar('T')
# RPC_E_CALL_REJECTED and RPC_E_SERVERCALL_RETRYLATER.
AUTO_CAD_BUSY_HRESULTS = {-2147418111, -2147417846}


def com_hresult(exc: BaseException) -> int | None:
    """Extract a signed HRESULT from a pywintypes.com_error-like exception."""
    value = getattr(exc, 'hresult', None)
    if value is None and getattr(exc, 'args', ()):
        value = exc.args[0]
    if not isinstance(value, int):
        return None
    return value - (1 << 32) if value > 0x7fffffff else value


def cad_com_retry(action: Callable[[], T], stage: str, *, timeout_s: float = 45.0,
                  interval_s: float = 0.6,
                  on_retry: Callable[[str], None] | None = None,
                  pump_messages: Callable[[], object] | None = None) -> T:
    """Retry transient AutoCAD COM rejections only; preserve fatal exceptions.

    Calls are made by one dedicated STA worker thread. A failure during InsertBlock
    may have ambiguous side effects on rare COM transport faults, so users must
    review draft drawings (the app never claims electrical validity).
    """
    deadline = time.monotonic() + timeout_s
    attempts = 0
    while True:
        try:
            return action()
        except Exception as exc:
            hr = com_hresult(exc)
            if hr not in AUTO_CAD_BUSY_HRESULTS:
                raise RuntimeError(f'AutoCAD step failed: {stage}: {exc}') from exc
            attempts += 1
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f'AutoCAD stayed busy during {stage} for {timeout_s:.0f} seconds '
                    f'({attempts} retries). Close any AutoCAD dialogs, cancel active '
                    'commands with Esc, then retry the CAD draft.'
                ) from exc
            if on_retry is not None and (attempts == 1 or attempts % 5 == 0):
                on_retry(f'AutoCAD busy during {stage}; waiting / retrying ({attempts})...')
            if pump_messages is not None:
                pump_messages()
            time.sleep(min(interval_s, max(0.0, deadline - time.monotonic())))



def show_autocad_best_effort(application, *, on_warning=None):
    """Try to reveal AutoCAD, but do not block document/ModelSpace operations.

    Some AutoCAD COM servers expose Visible as read-only or reject its setter
    even while Documents.Add and ModelSpace.InsertBlock are usable. A visibility
    failure is a UI concern, not a drawing failure; the subsequent CAD stages
    remain individually checked and are allowed to raise errors.
    """
    try:
        application.Visible = True
        return True
    except Exception as exc:
        if on_warning is not None:
            on_warning(
                'AutoCAD visibility setting was refused (non-fatal): '
                f'{type(exc).__name__}: {exc}. Continuing with document creation...'
            )
        return False


def insert_draft(plan_json: str | Path, template_dwt: str | Path, output_dwg: str | Path,
                 *, bay_pitch: float = 130.0,
                 on_progress: Callable[[str], None] | None = None) -> str:
    """Open AutoCAD, add DWT, insert DWGs by vertices, save an UNCONNECTED draft."""
    if os.name != 'nt':
        raise RuntimeError('AutoCAD COM drawing requires Windows + installed full AutoCAD')
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise RuntimeError('Install pywin32 on Windows for AutoCAD integration') from exc

    plan = json.loads(Path(plan_json).read_text(encoding='utf-8'))
    output_dwg, template_dwt = Path(output_dwg), Path(template_dwt)
    if not template_dwt.is_file():
        raise FileNotFoundError(f'AutoCAD DWT template not found: {template_dwt}')
    if output_dwg.exists():
        raise FileExistsError(f'Drawing already exists. Choose a new filename: {output_dwg}')
    for name, data in plan['components'].items():
        if data['quantity'] is None:
            raise ValueError(f'{name} quantity is unknown: confirm GIS counts before CAD')
        if not Path(data['dwg']).is_file():
            raise FileNotFoundError(f'Missing vendor DWG for {name}: {data["dwg"]}')

    from cad.geometry import create_balanced_placements, create_draft_placements
    placements = (create_balanced_placements(plan['components'], plan['bay_layout'], bay_pitch=bay_pitch)
                  if 'bay_layout' in plan else create_draft_placements(plan['components'], bay_pitch=bay_pitch))

    def log(message: str):
        if on_progress is not None:
            on_progress(message)

    pythoncom.CoInitialize()  # Each background thread needs its own COM apartment.
    try:
        def retry(action, stage, seconds=45):
            return cad_com_retry(action, stage, timeout_s=seconds,
                                 on_retry=log, pump_messages=pythoncom.PumpWaitingMessages)

        log('Connecting to running AutoCAD, or launching the installed default release...')
        try:
            application = retry(lambda: win32com.client.GetActiveObject('AutoCAD.Application'),
                                'attach to running AutoCAD', seconds=15)
        except RuntimeError as exc:
            # Launch only if the COM Running Object Table does not have AutoCAD.
            cause = exc.__cause__
            if com_hresult(cause) not in (-2147221021,):  # MK_E_UNAVAILABLE
                raise
            application = retry(lambda: win32com.client.Dispatch('AutoCAD.Application'),
                                'start AutoCAD', seconds=60)
        # AutoCAD 2022+ may open normally but reject its Visible property setter.
        # This must NOT prevent the template or blocks from being created.
        show_autocad_best_effort(application, on_warning=log)
        log(f'Opening drawing template in AutoCAD: {template_dwt.name}')
        drawing = retry(lambda: application.Documents.Add(str(template_dwt.resolve())),
                        'open DWT template', seconds=90)
        model = retry(lambda: drawing.ModelSpace, 'access ModelSpace')
        log(f'AutoCAD ready. Inserting {len(placements)} symbol blocks...')
        for index, placement in enumerate(placements, 1):
            name = placement['component']
            local = placement['insert']
            point = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8,
                                           [float(local['x']), float(local['y']), 0.0])
            block_file = str(Path(plan['components'][name]['dwg']).resolve())
            log(f'Inserting block {index}/{len(placements)}: {name} ({Path(block_file).name})')
            retry(lambda point=point, block_file=block_file: model.InsertBlock(
                point, block_file, 1.0, 1.0, 1.0, 0.0),
                f'insert block {index}/{len(placements)} ({name})', seconds=60)
            if index == len(placements) or index % 5 == 0:
                log(f'AutoCAD: inserted {index}/{len(placements)} blocks')

        output_dwg.parent.mkdir(parents=True, exist_ok=True)
        log('Saving AutoCAD draft...')
        retry(lambda: drawing.SaveAs(str(output_dwg.resolve())), 'save DWG', seconds=90)
        log(f'CAD draft saved: {output_dwg}')
        return str(output_dwg)
    finally:
        pythoncom.CoUninitialize()
