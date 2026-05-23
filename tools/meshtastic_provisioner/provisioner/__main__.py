from __future__ import annotations

import sys
from pathlib import Path


def _resolve_main():
    try:
        from .gui import main as app_main
    except ImportError:
        # Supports direct launches such as:
        #   python tools/meshtastic_provisioner/provisioner/__main__.py
        package_root = Path(__file__).resolve().parents[1]
        if str(package_root) not in sys.path:
            sys.path.insert(0, str(package_root))
        from provisioner.gui import main as app_main
    return app_main


if __name__ == "__main__":
    _resolve_main()()
