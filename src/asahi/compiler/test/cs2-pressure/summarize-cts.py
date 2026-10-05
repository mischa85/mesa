#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Keep CTS outcomes separate and verify actual spill-generating pass coverage."""
import argparse
import collections
import csv
import json
import re
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('output', type=Path)
p.add_argument('--require-spills', action='store_true')
a = p.parse_args()
results = {}
with (a.output / 'results/results.csv').open() as f:
    for row in csv.reader(f):
        results[row[0]] = row[1]
counts = collections.Counter(results.values())
spilling = collections.defaultdict(collections.Counter)
totals = collections.Counter()
pattern = re.compile(r'^APPLE9_CODEGEN stage=(\d+).* saves=(\d+) fills=(\d+)')
for log in (a.output / 'compiler').glob('*.log'):
    casefile = log.with_suffix('.cases')
    # Runner discovery invocations have no caselist.
    cases = casefile.read_text().splitlines() if casefile.exists() else []
    for line in log.open(errors='replace'):
        m = pattern.match(line)
        if not m:
            continue
        stage, saves, fills = map(int, m.groups())
        totals['saves'] += saves
        totals['fills'] += fills
        # Only single-case processes establish per-case spill coverage.
        if len(cases) == 1:
            spilling[cases[0]]['saves'] += saves
            spilling[cases[0]]['fills'] += fills
covered = {case: dict(n) for case, n in spilling.items()
           if n['saves'] and n['fills']}
passed = [case for case in covered if results.get(case) == 'Pass']
out = dict(outcomes=dict(counts), generated_transfers=dict(totals),
           cases_with_save_and_fill=covered,
           passing_cases_with_save_and_fill=passed,
           coverage_note='Main-program compiler output; totals include retries. '
                         'Only single-case processes establish case coverage.')
(a.output / 'summary.json').write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps(dict(outcomes=dict(counts), generated_transfers=dict(totals),
                     passing_cases_with_save_and_fill=len(passed))))
if a.require_spills and not passed:
    raise SystemExit('No passing single-case run compiled both SAVE and FILL; '
                     'this run does not validate forced spilling.')
