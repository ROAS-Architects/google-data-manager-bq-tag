#!/usr/bin/env python3
"""Copy template.js into template.tpl's ___SANDBOXED_JS_FOR_SERVER___ section.

GTM only ever runs the copy inside template.tpl. Run this after every edit to
template.js; scripts/check-tpl-sync.py fails the build if you forget.
"""
import io
import re
import sys

tpl = io.open('template.tpl', encoding='utf-8').read()
js = io.open('template.js', encoding='utf-8').read()

m = re.search(r'^___SANDBOXED_JS_FOR_SERVER___\n\n(.*?)\n\n\n^___', tpl, re.S | re.M)
if not m:
    sys.exit('sync-tpl: no ___SANDBOXED_JS_FOR_SERVER___ section in template.tpl')

io.open('template.tpl', 'w', encoding='utf-8').write(tpl[:m.start(1)] + js.strip() + tpl[m.end(1):])
print('sync-tpl: template.tpl updated from template.js')
