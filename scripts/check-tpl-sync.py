#!/usr/bin/env python3
"""Fail if template.tpl's embedded server JS has drifted from template.js.

GTM only ever runs the copy inside template.tpl. template.js exists so the code
is reviewable and diffable. A desynced pair is the standard way one of these
repos ships a fix that never reaches anybody.
"""
import io
import re
import sys

tpl = io.open('template.tpl', encoding='utf-8').read()
js = io.open('template.js', encoding='utf-8').read()

m = re.search(r'^___SANDBOXED_JS_FOR_SERVER___\n(.*?)\n^___', tpl, re.S | re.M)
if not m:
    sys.exit('check-tpl-sync: no ___SANDBOXED_JS_FOR_SERVER___ section in template.tpl')

if m.group(1).strip() != js.strip():
    sys.exit(
        'check-tpl-sync: template.tpl embedded JS differs from template.js.\n'
        'Copy template.js into the ___SANDBOXED_JS_FOR_SERVER___ section and commit both.'
    )

for needed, where, label in (
    ('logToBigQuery', js, 'template.js'),
    ('access_bigquery', tpl, 'template.tpl'),
):
    if needed not in where:
        sys.exit(
            'check-tpl-sync: %s is missing from %s. '
            'The BigQuery logging this fork exists for is gone.' % (needed, label)
        )

print('check-tpl-sync: ok')
