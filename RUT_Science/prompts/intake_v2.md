Extract a research specification proposal from latest_user_text. Do not execute or
confirm. Output exactly schema_version, fields, missing_required, conflicts, questions.
schema_version="intake_proposal_v2". Each fields entry contains value, source, evidence.
source=user requires verbatim evidence from latest_user_text. Optional defaults use
source=suggestion and empty evidence. Preserve current_draft unless explicitly changed.
Allowed fields: dataset_name (generated or Darcy), target (regression_output or
pressure_field), objective_metric (mean_relative_l2), quality_threshold, compute_units,
allowed_method_family (mean_ridge). Use the fixed catalog target mapping when user
clearly requests the registered task. Ask only blocking questions. Unsupported targets
or methods are conflicts; never silently map them to a supported task.
