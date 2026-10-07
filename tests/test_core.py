import unittest

from http_link_header_parser import Link, LinkHeaderParser, parse_link_header


class TestParser(unittest.TestCase):
    def test_single_link_no_params(self):
        links = parse_link_header("<https://api.example/items/42>")
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].href, "https://api.example/items/42")
        self.assertEqual(links[0].params, {})

    def test_rel_type_title(self):
        header = (
            '<https://cdn.example/font.woff2>; '
            'rel="preload"; as="font"; type="font/woff2"; '
            'title="Primary webfont"'
        )
        links = parse_link_header(header)
        self.assertEqual(len(links), 1)
        link = links[0]
        self.assertEqual(link.href, "https://cdn.example/font.woff2")
        self.assertEqual(link.rel, "preload")
        self.assertEqual(link.params["type"], "font/woff2")
        self.assertEqual(link.params["title"], "Primary webfont")
        self.assertEqual(link.params["as"], "font")

    def test_anchor_param(self):
        links = parse_link_header(
            '<https://vocab.example/term>; rel="glossary"; '
            'anchor="https://doc.example/section-3"'
        )
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].anchor, "https://doc.example/section-3")
        self.assertEqual(links[0].rel, "glossary")

    def test_multiple_links(self):
        header = (
            '<https://api.example/next>; rel="next", '
            '<https://api.example/prev>; rel="prev"'
        )
        links = parse_link_header(header)
        self.assertEqual(len(links), 2)
        self.assertEqual(links[0].href, "https://api.example/next")
        self.assertEqual(links[0].rel, "next")
        self.assertEqual(links[1].href, "https://api.example/prev")
        self.assertEqual(links[1].rel, "prev")

    def test_param_name_case_insensitive(self):
        links = parse_link_header('<https://x.example/>; REL="canonical"')
        self.assertEqual(links[0].rel, "canonical")
        self.assertIn("rel", links[0].params)

    def test_multiple_rel_tokens(self):
        links = parse_link_header(
            '<https://s.example/>; rel="alternate http://example.net/foo"'
        )
        self.assertEqual(links[0].rel, "alternate http://example.net/foo")

    def test_parse_by_rel_matches_token(self):
        header = (
            '<https://a.example/>; rel="next", '
            '<https://b.example/>; rel="prev alternate"'
        )
        parser = LinkHeaderParser()
        alts = parser.parse_by_rel(header, "alternate")
        self.assertEqual(len(alts), 1)
        self.assertEqual(alts[0].href, "https://b.example/")

    def test_parse_by_rel_case_insensitive(self):
        header = '<https://a.example/>; rel="NEXT"'
        self.assertEqual(len(LinkHeaderParser().parse_by_rel(header, "next")), 1)

    def test_unquoted_param_value(self):
        links = parse_link_header(
            '<https://a.example/>; rel=preload; type=application/json'
        )
        self.assertEqual(links[0].rel, "preload")
        self.assertEqual(links[0].params["type"], "application/json")

    def test_extension_param_preserved(self):
        links = parse_link_header('<https://a.example/>; rel=preconnect; crossorigin')
        self.assertEqual(links[0].params.get("crossorigin"), "")

    def test_escaped_quote_in_value(self):
        links = parse_link_header(
            '<https://a.example/>; title="say \\\"hi\\\" now"'
        )
        self.assertEqual(links[0].params["title"], 'say "hi" now')

    def test_list_of_headers_joined(self):
        links = parse_link_header(
            ['<https://a.example/>; rel="next"', '<https://b.example/>; rel="prev"']
        )
        self.assertEqual([l.rel for l in links], ["next", "prev"])

    def test_whitespace_tolerance(self):
        header = '  <https://a.example/>  ;  rel="next"  ,  <https://b.example/> ; rel="prev"  '
        links = parse_link_header(header)
        self.assertEqual(len(links), 2)
        self.assertEqual(links[0].rel, "next")
        self.assertEqual(links[1].rel, "prev")

    def test_empty_header(self):
        self.assertEqual(parse_link_header(""), [])

    def test_link_equality_and_hash(self):
        a = Link(href="https://x/", params={"rel": "next"})
        b = Link(href="https://x/", params={"rel": "next"})
        c = Link(href="https://x/", params={"rel": "prev"})
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertEqual(len({a, b, c}), 2)

    def test_link_getattr_for_unknown_param(self):
        link = Link(href="https://x/", params={"rel": "next", "x-custom": "abc"})
        self.assertEqual(getattr(link, "x-custom"), "abc")
        # __getattr__ only resolves names present in params.
        with self.assertRaises(AttributeError):
            getattr(link, "missing")

    def test_duplicate_param_joined(self):
        links = parse_link_header(
            '<https://a.example/>; rel="next"; rel="preload"'
        )
        self.assertEqual(links[0].rel, "next preload")


if __name__ == "__main__":
    unittest.main()
