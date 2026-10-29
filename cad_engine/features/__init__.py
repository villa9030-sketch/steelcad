from . import dress, extrude, hole, revolve
from .. import sheetmetal
from ..sheetmetal import shapes
from ..sheetmetal import forms
from ..sheetmetal import edge_flange, linguetta_piegata
from ..sheetmetal import taglio_testa
from ..importers import step_assieme, step_lamiera

BUILDERS = {
    'extrude': extrude.build,
    'revolve': revolve.build,
    'hole': hole.build,
    'fillet': dress.build,
    'chamfer': dress.build,
    'sheet': sheetmetal.build,
    'sheet_shape': shapes.build_shape,
    'sheet_cut': sheetmetal.build_cut,
    'sheet_form': forms.build_form,
    'sheet_edge_flange': edge_flange.build_edge_flange,
    'sheet_tab_fold': linguetta_piegata.build,
    'sheet_miter': taglio_testa.build_end_miter,
    'step_lamiera': step_lamiera.build,
    'solido_step': step_assieme.build_solido,
}

# campi che contengono valori (numeri o espressioni sui parametri)
VALUE_FIELDS = {
    'extrude': ('distance',),
    'revolve': ('angle',),
    'hole': ('diameter', 'depth'),
    'fillet': ('radius',),
    'chamfer': ('distance',),
    'sheet': ('thickness', 'radius', 'k', 'bd90'),
    'sheet_shape': ('thickness', 'radius', 'k', 'd1', 'd2', 'height', 'a', 'b', 'd', 'ex', 'ey', 'pitch', 'length', 'hits'),
    'sheet_form': ('width', 'height', 'depth'),
    'sheet_edge_flange': ('length', 'angle', 'trim0', 'trim1'),
    'sheet_tab_fold': ('angle',),
    'sheet_miter': ('angle', 'gap'),
    'step_lamiera': ('k', 'spessore'),
}
