from . import dress, extrude, hole, revolve
from .. import sheetmetal
from ..sheetmetal import shapes
from ..sheetmetal import forms

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
}
