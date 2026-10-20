def classify_failures(case, run, checks):
    failures=[]
    if not checks['intent_correct']: failures.append('WRONG_INTENT')
    if not checks['tool_selection_correct']:
        actual=[x.tool_name for x in run.state.tool_calls]
        expected=case.expected_tools
        if any(x not in expected for x in actual): failures.append('EXTRA_TOOL')
        if any(x not in actual for x in expected): failures.append('MISSING_TOOL')
        failures.append('WRONG_TOOL')
    if not checks['tool_sequence_correct']: failures.append('WRONG_TOOL_SEQUENCE')
    if not checks['argument_correct_after_repair']: failures.append('WRONG_ARGUMENT')
    if any(x.error_code=='ARGUMENT_REPAIR_FAILED' for x in run.state.tool_calls): failures.append('ARGUMENT_REPAIR_FAILED')
    if not checks['task_success']: failures.append('TASK_FAILED')
    if not checks['scope_safe']: failures.append('SCOPE_VIOLATION')
    if not checks['no_hallucinated_value']: failures.append('HALLUCINATED_VALUE')
    if not checks['evidence_grounded']: failures.append('EVIDENCE_IRRELEVANT')
    if not checks['no_unsupported_claim']: failures.append('UNSUPPORTED_CLAIM')
    return list(dict.fromkeys(failures))
