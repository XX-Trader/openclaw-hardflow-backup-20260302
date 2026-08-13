import importlib.util
import sys
from pathlib import Path


SCRIPT_DIR = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "library"
    / "ui-ux-pro-max"
    / "scripts"
)
SCRIPT_PATH = SCRIPT_DIR / "design_system.py"


def load_design_system_module():
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        spec = importlib.util.spec_from_file_location("ui_ux_design_system", SCRIPT_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPT_DIR))


def test_format_markdown_splits_anti_patterns_into_bullets():
    module = load_design_system_module()

    output = module.format_markdown(
        {
            "project_name": "Regression",
            "anti_patterns": "Dense layout + Low contrast",
        }
    )

    assert "### Avoid (Anti-patterns)" in output
    assert "- Dense layout\n- Low contrast" in output
