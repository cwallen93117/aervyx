import runpy
from pathlib import Path


def test_entrypoint_resolves_when_launched_as_file():
    entrypoint = Path(__file__).resolve().parents[1] / "provisioner" / "__main__.py"
    namespace = runpy.run_path(str(entrypoint), run_name="provisioner_entrypoint_test")

    assert namespace["_resolve_main"]().__name__ == "main"
