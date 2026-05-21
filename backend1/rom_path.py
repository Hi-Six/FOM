"""metrics/rom 을 sys.path에 올려 domain.domain1 import 가 가능하게 한다."""

import sys
from pathlib import Path

_ROM_ROOT = Path(__file__).resolve().parent / "metrics" / "rom"


def ensure_rom_domain_on_path() -> Path:
    """backend1/routers 가 rom/routers 보다 먼저 잡히도록 append 한다."""
    root = str(_ROM_ROOT)
    if root not in sys.path:
        sys.path.append(root)
    return _ROM_ROOT
