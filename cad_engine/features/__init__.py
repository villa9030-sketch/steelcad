from . import dress, extrude, hole
from .. import sheetmetal

BUILDERS = {
    'extrude': extrude.build,
    'hole': hole.build,
    'fillet': dress.build,
    'chamfer': dress.build,
    'sheet': sheetmetal.build,
    'sheet_cut': sheetmetal.build_cut,
}

# campi che contengono valori (numeri o espressioni sui parametri)
VALUE_FIELDS = {
    'extrude': ('distance',),
    'hole': ('diameter', 'depth'),
    'fillet': ('radius',),
    'chamfer': ('distance',),
    'sheet': ('thickness', 'radius', 'k', 'bd90'),
}
