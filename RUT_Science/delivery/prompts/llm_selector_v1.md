Return exactly schema_version="action_selection_v1", observation_ref, action_id,
evidence_refs, reason. Choose one legal candidate ID from the supplied public observation.
You may not modify parameters. Reason must be concise and evidence-based. Evidence refs
must be observed experiment candidate_ref values, or empty. Do not assume unobserved
errors. Balance experiment, diagnostic and recovery costs. submit_best freezes the
lowest validation-error model and ends decisions; sealed evaluation cannot guide further
actions. abstain is not success. Only the host can change budgets or confirm.
