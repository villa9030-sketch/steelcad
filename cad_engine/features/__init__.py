from . import dress, extrude, hole
from .. import sheetmetal
from ..sheetmetal import forms

BUILDERS = {
    'extrude': extrude.build,
    'hole': hole.build,
    'fillet': dress.build,
    'chamfer': dress.build,
    'sheet': sheetmetal.build,
    'sheet_cut': sheetmetal.build_cut,
    'sheet_form': forms.build_form,
}

# campi che contengono valori (numeri o espressioni sui parametri)
VALUE_FIELDS = {
    'extrude': ('distance',),
    'hole': ('diameter', 'depth'),
    'fillet': ('radius',),
    'chamfer': ('distance',),
    'sheet': ('thickness', 'radius', 'k', 'bd90'),
    'sheet_form': ('width', 'height', 'depth'),
}
