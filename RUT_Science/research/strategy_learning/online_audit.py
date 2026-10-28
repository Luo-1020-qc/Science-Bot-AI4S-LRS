"""Post-cleanup G2.4 audit; original freeze is checked without old delivery paths."""
import json
from pathlib import Path
from audit import verify_study

def audit_g24():
    value = verify_study(Path(__file__).resolve().parent/"studies/g2_4")
    print(json.dumps(value))
    return value

if __name__ == "__main__": audit_g24()
