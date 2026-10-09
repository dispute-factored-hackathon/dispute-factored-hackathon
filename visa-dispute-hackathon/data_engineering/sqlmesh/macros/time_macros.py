from sqlglot import exp
from sqlmesh import macro
from sqlmesh.core.macros import MacroEvaluator


@macro()
def NOW_IN_BOGOTA_TZ(evaluator: MacroEvaluator) -> exp.Expression:
    """Returns the current time in the America/Bogota timezone."""
    return exp.AtTimeZone(this=exp.func("NOW"), zone=exp.Literal.string("America/Bogota"))
