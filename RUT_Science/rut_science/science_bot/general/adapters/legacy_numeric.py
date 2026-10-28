"""Bridge the existing audited numeric engine into a general session.

Scientific evidence, checkpoints and job reconciliation remain owned by the
original ScienceSession. Model history and admitted request/token counts are
shared with the parent conversation so switching tasks cannot reset its budget.
"""
import json
from pathlib import Path

from ...contracts import BudgetedResearchSpec
from ...llm import ScienceLLM
from ...session import ScienceSession


def _attach(parent, child):
    ledger_path = parent.folder/"llm_ledger.json"
    child.llm = ScienceLLM(child, history_folder=parent.folder, ledger_path=ledger_path)
    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        child.env.state.update(requests=ledger["requests"], tokens=ledger["accounted_tokens"])
    child.event_callback = lambda event: parent.emit(event["kind"], event["payload"])
    return child


def prepare_numeric(parent, dataset, budget=10, quality_threshold=.2, *, spec=None):
    """Create a reviewable numeric draft only for an explicitly selected dataset."""
    if dataset not in {"generated", "darcy"}:
        raise ValueError("Numeric adapter requires a registered explicit dataset")
    spec = spec or BudgetedResearchSpec(dataset=dataset, split="demo", compute_units=budget,
                               quality_threshold=quality_threshold,
                               llm_requests=parent.limits.get("llm_requests", 12),
                               llm_tokens=parent.limits.get("llm_tokens", 60000))
    if not isinstance(spec, BudgetedResearchSpec) or spec.dataset != dataset:
        raise ValueError("Explicit numeric specification does not match its selected dataset")
    experiments = parent.folder.resolve()/"experiments"
    if experiments.resolve() != experiments:
        raise ValueError("Numeric experiment state must not be redirected")
    child = ScienceSession.create(experiments, backend=parent.meta["backend"],
                                 planner=parent.meta["planner"], checkpoint=parent.meta.get("checkpoint"),
                                 model=parent.meta["model"], spec=spec,
                                 workspace=parent.workspace.root if parent.workspace else None)
    child = _attach(parent, child)
    child.save()
    return child


def restore_numeric(parent, relative_folder):
    """Restore the recorded child while keeping its evidence inside this session."""
    if not isinstance(relative_folder, str) or not relative_folder.strip():
        raise ValueError("Numeric session requires a relative folder")
    relative = Path(relative_folder)
    if relative.is_absolute() or relative.drive or ".." in relative.parts:
        raise ValueError("Numeric session folder must stay inside the conversation")
    root = parent.folder.resolve()
    folder = (root/relative).resolve()
    if folder == root or not folder.is_relative_to(root/"experiments"):
        raise ValueError("Numeric session folder must stay inside conversation experiments")
    child = ScienceSession.restore(folder, workspace=parent.workspace.root if parent.workspace else None)
    return _attach(parent, child)
