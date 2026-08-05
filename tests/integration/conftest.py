# conftest for integration tests — adds precision-gate-core to sys.path
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
PRECISION_GATE_ROOT = REPO_ROOT / "products" / "precision-gate-core"
QUINTA_ORDEM_ROOT = REPO_ROOT / "products" / "quinta-ordem-gate" / "src"

for p in (str(PRECISION_GATE_ROOT), str(QUINTA_ORDEM_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)
