"""AUTO-MAS plugin compatibility blackbox test tools (Subagent A).

Runs 12 checks against the wheelhouse plugin distributions:
  1-2  static (zipfile METADATA + entry_points.txt)
  3-6  runtime (install + import + entry-point load + schema dump)
  7-12 lifecycle (activate/update/rollback, deactivate, double-load,
           missing-dep error, plugin-exception isolation, config v2 / WS leak)
"""
