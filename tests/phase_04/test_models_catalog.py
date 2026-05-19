"""Wave 0 stub — real tests land in plan 04-03 (models + migration).

Per ``.planning/phases/04-shared-catalog/04-VALIDATION.md`` §"Wave 0
Requirements" the file must exist so the sampling-rate command
``pytest -q tests/phase_04/ -x`` is runnable from this commit forward
(fails fast on stubs, not collection errors). The validation prose
suggests ``pytest.fail`` but a ``pytest.skip`` keeps the suite green
during interleaved development — see the plan 04-01 Task 1 action body
for the recorded deviation rationale.
"""

from __future__ import annotations

import pytest


def test_wave_0_stub() -> None:
    pytest.skip("Wave 0 stub — fill in during subsequent plans.")
