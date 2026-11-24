"""Regression test for layout/run_flow.sh EXIT-trap composition (issue #365).

bash keeps one handler per signal, so a second `trap ... EXIT` silently
replaces the first and leaks the earlier scratch dir. Assert the script
carries exactly one EXIT trap, that it names both scratch paths, and that the
late-bound request path is default-guarded (`:-`) so an exit before its
assignment still lets `rm -rf "${WORK}"` run under `set -u`.
"""

import re
import unittest
from pathlib import Path

FLOW = Path(__file__).resolve().parents[2] / "layout" / "run_flow.sh"


class RunFlowTrapTest(unittest.TestCase):
    def setUp(self):
        self.traps = re.findall(r"^\s*trap\s+.*\bEXIT\b.*$",
                                FLOW.read_text(), re.M)

    def test_exactly_one_exit_trap(self):
        self.assertEqual(len(self.traps), 1, self.traps)

    def test_trap_covers_both_scratch_paths(self):
        self.assertIn("${WORK}", self.traps[0])
        self.assertIn("PEX_ROW4_REQUEST", self.traps[0])

    def test_late_bound_path_is_default_guarded(self):
        self.assertIn("${PEX_ROW4_REQUEST:-}", self.traps[0])


if __name__ == "__main__":
    unittest.main()
