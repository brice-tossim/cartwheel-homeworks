# None deterministic

> uv run python scripts/prompt_trials.py

run 1: issue_refund       tools=['get_order', 'issue_refund']
run 2: issue_refund       tools=['get_order', 'issue_refund']
run 3: issue_refund       tools=['get_order', 'issue_refund', 'search_help_center']
run 4: issue_refund       tools=['get_order', 'issue_refund', 'escalate_to_human']
run 5: issue_refund       tools=['get_order', 'issue_refund']

tally: {'issue_refund': 5}
records: esc1_before.json

> uv run python scripts/prompt_trials.py

run 1: issue_refund       tools=['get_order', 'issue_refund', 'escalate_to_human']
run 2: issue_refund       tools=['get_order', 'issue_refund', 'escalate_to_human']
run 3: issue_refund       tools=['get_order', 'issue_refund']
run 4: issue_refund       tools=['get_order', 'issue_refund', 'escalate_to_human']
run 5: issue_refund       tools=['get_order', 'issue_refund']

tally: {'issue_refund': 5}
records: esc1_before.json
