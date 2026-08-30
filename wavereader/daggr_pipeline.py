"""Fixed "Morning Surf Report" DAG visualised with daggr.

Daggr is beta and has NO conditional branching: this visualises the fixed
morning pipeline only, never the dynamic chat agent loop.
"""

from __future__ import annotations


def build_pipeline() -> object:
    """Assemble the fixed morning-report DAG.

    TODO: nodes for pick-region -> fetch forecasts -> score -> summarise,
    rendered on the daggr canvas.
    """
    raise NotImplementedError
