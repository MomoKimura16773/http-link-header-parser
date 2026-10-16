# http_link_header_parser

Parse HTTP Link headers (RFC 8288) into structured Python objects with zero
dependencies.

```python
from http_link_header_parser import LinkHeaderParser, parse_link_header

links = parse_link_header('<https://api.example/next>; rel="next"')
parser = LinkHeaderParser()
prev = parser.parse_by_rel(
    '<https://a.example/>; rel="next", <https://b.example/>; rel="prev"',
    "prev",
)[0]
print(prev.href, prev.rel)
```

## Why this exists

Web framework Link header helpers tend to either over-parse (returning only
`rel` and dropping extension parameters) or under-parse (returning raw
dicts keyed by `rel`). This library returns a `Link` with the target URI and
all parameters preserved, while still offering `parse_by_rel` for the common
case of looking up a relation. The trade-off is that duplicate parameters are
joined with a space rather than returned as a list; this matches how
multi-valued `rel` is serialised in RFC 8288, but it does mean a parameter
that legitimately appears twice with different semantics loses ordering.

## Edge cases

- Parameter names are case-insensitive per RFC 8288 §3 and normalised to
  lowercase, so `Rel` and `rel` are stored under `params["rel"]`.
- Quoted-string backslash escapes are unescaped one layer (e.g.
  `title="say \"hi\""` becomes `say "hi"`).
- Unquoted parameter values are accepted, as real-world headers frequently
  omit quotes for tokens like `rel=preload`.
- A parameter with no `=` (e.g. `crossorigin`) is stored with an empty string
  value.

Run tests with `PYTHONPATH=src python -m unittest discover -s tests`.

## Design notes

The window stores values eagerly rather than keeping running aggregates. Running
sums drift with floating point over long streams, and recomputing from a small
buffer is cheap enough that the drift is not worth the speed.

