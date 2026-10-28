"""Use the common current auditor without rewriting historic run proofs."""
import importlib.util
from .guard import LAB


def verify_current():
    path = LAB.parents[1]/"audit.py"
    specification = importlib.util.spec_from_file_location("consolidated_research_audit", path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module.verify_study(LAB)
