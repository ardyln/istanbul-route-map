"""unwrap.py <soap response xml> <out json>: the JSON İBB's *_json SOAP operations wrap in their result element."""
import html
import json
import re
import sys

src, out = sys.argv[1:3]
text = open(src, encoding="utf-8").read()
m = re.search(r"_jsonResult>(.*)</Get\w+_jsonResult>", text, re.S)
if not m:
    sys.exit(f"{src}: no JSON result in the response (İBB refused or changed?): {text[:300]}")
json.dump(json.loads(html.unescape(m.group(1))), open(out, "w", encoding="utf-8"), ensure_ascii=False)
