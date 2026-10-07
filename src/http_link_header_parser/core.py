from __future__ import annotations

from typing import Dict, List, Optional, Union
import re

__all__ = ["Link", "LinkHeaderParser", "parse_link_header"]


class Link:
    """Structured representation of a single link from an RFC 8288 Link header.

    Parameters are stored as a plain dict so callers can introspect extension
    attributes without a dedicated attribute for every possible parameter.
    """

    def __init__(self, href: str, params: Dict[str, str]):
        self.href = href
        self.params = dict(params)

    def __getattr__(self, name: str) -> str:
        # Convenience access for known parameters without hardcoding them as
        # attributes. Only applied when the attribute is absent so __init__'s
        # direct assignments still work.
        params = self.__dict__.get("params")
        if params is None:
            raise AttributeError(name)
        if name in params:
            return params[name]
        raise AttributeError(name)

    @property
    def rel(self) -> Optional[str]:
        # "rel" is usually singular; expose the first value when present.
        return self.params.get("rel")

    @property
    def anchor(self) -> Optional[str]:
        return self.params.get("anchor")

    def __repr__(self) -> str:
        return f"Link(href={self.href!r}, params={self.params!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Link):
            return NotImplemented
        return self.href == other.href and self.params == other.params

    def __hash__(self) -> int:
        return hash((self.href, tuple(sorted(self.params.items()))))


def _unescape(s: str) -> str:
    """Strip a single layer of backslash escaping per RFC 8288 §3.

    We deliberately leave unknown escapes intact rather than raising, because
    parsers in the wild differ on this and raising rejects otherwise valid
    headers. A second layer of escaping is never applied.
    """
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\" and i + 1 < n:
            out.append(s[i + 1])
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


class _Scanner:
    """Cursor over the raw header string producing one token at a time.

    Centralising the cursor keeps the state machine in the parser readable and
    avoids duplicated index bookkeeping in three small parse routines.
    """

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.n = len(text)

    def eof(self) -> bool:
        return self.pos >= self.n

    def peek(self) -> str:
        if self.pos >= self.n:
            return ""
        return self.text[self.pos]

    def skip_ws(self) -> None:
        while self.pos < self.n and self.text[self.pos] in " \t":
            self.pos += 1

    def consume(self, ch: str) -> None:
        if self.pos >= self.n or self.text[self.pos] != ch:
            raise ValueError(f"Expected {ch!r} at position {self.pos}")
        self.pos += 1

    def consume_optional(self, ch: str) -> bool:
        if self.peek() == ch:
            self.pos += 1
            return True
        return False

    def read_target(self) -> str:
        self.skip_ws()
        self.consume("<")
        start = self.pos
        out = []
        while self.pos < self.n and self.text[self.pos] != ">":
            out.append(self.text[self.pos])
            self.pos += 1
        if self.pos >= self.n:
            raise ValueError("Unterminated target")
        self.pos += 1  # consume '>'
        raw = "".join(out)
        # Target chars between angle brackets are unescaped to allow \\> and
        # \\\\ to appear in URIs, matching common parser behaviour.
        return _unescape(raw)

    def read_param_name(self) -> str:
        start = self.pos
        while self.pos < self.n:
            c = self.text[self.pos]
            if c == "=" or c == ";" or c == "," or c in " \t":
                break
            self.pos += 1
        if self.pos == start:
            raise ValueError(f"Empty parameter name at {self.pos}")
        name = self.text[start:self.pos]
        # Parameter names are case-insensitive per RFC 8288 §3; normalise so
        # downstream lookups for "rel" vs "Rel" agree.
        return name.lower()

    def read_param_value(self) -> str:
        self.skip_ws()
        if self.consume_optional('"'):
            parts = []
            while self.pos < self.n:
                c = self.text[self.pos]
                if c == "\\" and self.pos + 1 < self.n:
                    parts.append(self.text[self.pos + 1])
                    self.pos += 2
                    continue
                if c == '"':
                    self.pos += 1
                    return "".join(parts)
                parts.append(c)
                self.pos += 1
            raise ValueError("Unterminated quoted string")
        # Unquoted token: stop at parameter/header separators or whitespace.
        start = self.pos
        while self.pos < self.n:
            c = self.text[self.pos]
            if c == ";" or c == "," or c in " \t":
                break
            self.pos += 1
        if self.pos == start:
            raise ValueError(f"Empty parameter value at {self.pos}")
        return self.text[start:self.pos]


class LinkHeaderParser:
    """Parse one or more RFC 8288 Link header values into Link objects."""

    def parse(self, header: Union[str, List[str]]) -> List[Link]:
        text = header if isinstance(header, str) else ", ".join(header)
        links: List[Link] = []
        s = _Scanner(text)
        while True:
            s.skip_ws()
            if s.eof():
                break
            href = s.read_target()
            params: Dict[str, str] = {}
            while True:
                s.skip_ws()
                if not s.consume_optional(";"):
                    break
                s.skip_ws()
                name = s.read_param_name()
                s.skip_ws()
                # A parameter with no '=' (e.g. crossorigin) is stored with an
                # empty string value, per the documented edge cases.
                if not s.consume_optional("="):
                    params[name] = ""
                    continue
                value = s.read_param_value()
                # Multiple rel values may appear within a single parameter;
                # multiple same-name params are preserved by joining with a
                # space, which is how RFC 8288 serialises multi-valued rel.
                if name in params:
                    params[name] = params[name] + " " + value
                else:
                    params[name] = value
            links.append(Link(href=href, params=params))
            s.skip_ws()
            if s.eof():
                break
            s.consume(",")
        return links

    def parse_by_rel(
        self, header: Union[str, List[str]], rel: str
    ) -> List[Link]:
        """Return links whose rel parameter contains the given relation.

        Relation tokens are matched case-insensitively because rel values are
        compared as case-insensitive tokens in RFC 8288 §3.3.1.
        """
        target = rel.lower()
        out = []
        for link in self.parse(header):
            r = link.params.get("rel")
            if not r:
                continue
            tokens = [t.lower() for t in r.split()]
            if target in tokens:
                out.append(link)
        return out


def parse_link_header(header: Union[str, List[str]]) -> List[Link]:
    """Module-level convenience wrapper around LinkHeaderParser().parse."""
    return LinkHeaderParser().parse(header)
