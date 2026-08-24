#!/usr/bin/env python3
"""Fail if template.tpl's embedded server JS has drifted from template.js.

GTM only ever runs the copy inside template.tpl. template.js exists so the code
is reviewable and diffable. A desynced pair is the standard way one of these
repos ships a fix that never reaches anybody.
"""
import io
import json
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

# Google caps a custom template at 100 fields, counting groups and labels, and
# upstream sits on that cap. Over it, templates.create returns "You have reached
# the maximum number of fields allowed" and nobody can install the template. An
# upstream release that adds a field is the way this breaks.
FIELD_LIMIT = 100

m = re.search(r'^___TEMPLATE_PARAMETERS___\n\n(\[.*?\n\])\n', tpl, re.S | re.M)
if not m:
    sys.exit('check-tpl-sync: no ___TEMPLATE_PARAMETERS___ section in template.tpl')


def count_fields(items):
    total = 0
    for item in items:
        total += 1
        sub = item.get('subParams')
        if isinstance(sub, list):
            total += count_fields(sub)
    return total


fields = count_fields(json.loads(m.group(1)))
if fields > FIELD_LIMIT:
    sys.exit(
        'check-tpl-sync: template.tpl declares %d fields, over Google\'s limit of %d. '
        'GTM will refuse to create it. Free fields before adding any.' % (fields, FIELD_LIMIT)
    )

print('check-tpl-sync: ok (%d/%d fields)' % (fields, FIELD_LIMIT))
