"""Spine-and-branch coordination planning (offline, additive to MACU).

This package implements *planning only*: it turns a task into a legalized
spine/branch dependency graph (operational fan-in <= 1, informational fan-in
unrestricted). It imports MACU helpers but modifies no existing MACU code.

See research/spine-branch-cua.md for the design.
"""

from utils.spine_branch.legalize import legalize_spine_branch  # noqa: F401
from utils.spine_branch.plan import generate_spine_branch_plan  # noqa: F401
