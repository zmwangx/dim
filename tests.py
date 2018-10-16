import re

import pytest

from dim import *


SAMPLE_HTML = """\
<html>
<head><!-- 1 -->
</head>
<body><!-- 2 -->
  <header><!-- 2.1 -->
  </header>
  <div id="body"><!-- 2.2 -->
    <main id="article"><!-- 2.2.1 -->
      <p id="p1"><!-- 2.2.1.1 -->
        Paragraph 1.
        <a href="/link1" title="internal link1"><!-- 2.2.1.1.1 -->
          Link 1.
        </a>
        <a href="/link2" title="internal link2"><!-- 2.2.1.1.2 -->
          Link 2.
        </a>
        <img src="/image.png" width="128" height="128"/><!-- 2.2.1.1.3 -->
      </p>
      <blockquote><!-- 2.2.1.2 -->
        <a href="/link3" title="internal link3"><!-- 2.2.1.2.1 -->
          Link 3.
        </a>
        <a href="https://example.com" hreflang="en-US" title="example.com link"><!-- 2.2.1.2.2 -->
          Example.
        </a>
      </blockquote>
      <p><!-- 2.2.1.3 -->
        Another paragraph.
      </p>
      <div data-desc="empty div"><!-- 2.2.1.4 --></div>
      <p data-desc="escapes"><!-- 2.2.1.5 -->
        Some escaped characters: &amp;&lt;&gt;&quot;&#x27;
      </p>
    </main>
    <nav id="sidebar" title="Navigation"><!-- 2.2.2 -->
    </nav>
    <aside id="ads"><!-- 2.2.3 -->
      <div class="first-party ad"><!-- 2.2.3.1 -->
      </div>
      <div class="ad first-party"><!-- 2.2.3.2 -->
      </div>
      <div class="ad"><!-- 2.2.3.3 -->
      </div>
      <div class="ad"><!-- 2.2.3.4 -->
      </div>
    </aside>
  </div>
  <footer><!-- 2.3 -->
  </footer>
</body>
</html>
"""


# Stripped HTML comments are attached to the latest preceding element
# (not necessarily closed) as annotation. If multiple annotations are
# found for a single element, the last one prevails.
class AnnotatedDOMBuilder(DOMBuilder):
    def handle_comment(self, comment):
        for node in reversed(self._stack):
            if isinstance(node, ElementNode):
                node.annotation = comment.strip()
                return


# Get annotations of a list of nodes.
def annotations(nodes):
    return [getattr(node, "annotation", None) for node in nodes]


@pytest.fixture(scope="module")
def tree():
    root = parse_html(SAMPLE_HTML, ParserClass=AnnotatedDOMBuilder)
    repr(root)
    return root


@pytest.mark.parametrize(
    "selector,matches",
    [
        ("header", ["2.1"]),
        ("#body", ["2.2"]),
        ("main#article", ["2.2.1"]),
        ("body > main#article", []),
        ("#article + #ads", []),
        ("#article ~ #ads", ["2.2.3"]),
        (".ad", ["2.2.3.1", "2.2.3.2", "2.2.3.3", "2.2.3.4"]),
        (".ad.first-party", ["2.2.3.1", "2.2.3.2"]),
        (".first-party.ad", ["2.2.3.1", "2.2.3.2"]),
        (".ad .first-party", []),
        ("span.ad", []),
        ("[title]", ["2.2.1.1.1", "2.2.1.1.2", "2.2.1.2.1", "2.2.1.2.2", "2.2.2"]),
        ("nav[title]", ["2.2.2"]),
        ("[title=Navigation]", ["2.2.2"]),
        ("[title='internal link1']", ["2.2.1.1.1"]),
        ('[title="internal link1"]', ["2.2.1.1.1"]),
        (
            "[title='internal link1'], [title='internal link2']",
            ["2.2.1.1.1", "2.2.1.1.2"],
        ),
        ("[title~=link]", ["2.2.1.2.2"]),
        ("[class|=first]", ["2.2.3.1"]),
        ("[hreflang|=en]", ["2.2.1.2.2"]),
        ("[hreflang|=en-]", []),
        ("[title^=internal]", ["2.2.1.1.1", "2.2.1.1.2", "2.2.1.2.1"]),
        ("[title$=' link']", ["2.2.1.2.2"]),
        ("[class$=ad]", ["2.2.3.1", "2.2.3.3", "2.2.3.4"]),
        ("[title*=link]", ["2.2.1.1.1", "2.2.1.1.2", "2.2.1.2.1", "2.2.1.2.2"]),
        ("#body p", ["2.2.1.1", "2.2.1.3", "2.2.1.5"]),
        ("#body p[id]", ["2.2.1.1"]),
        ("#body > p[id]", []),
        ("#body > * > p[id]", ["2.2.1.1"]),
        ("img[src='/image.png']", ["2.2.1.1.3"]),
    ],
)
def test_selector(tree, selector, matches):
    repr(SelectorGroup.from_str(selector))
    assert annotations(tree.select_all(selector)) == matches
    if matches:
        assert tree.select(selector).annotation == matches[0]
    else:
        assert tree.select(selector) is None
    for node in tree.select_all(selector):
        assert node.matched_by(selector)


def test_non_root_selection(tree):
    assert annotations(tree.select("#p1").select_all("a")) == ["2.2.1.1.1", "2.2.1.1.2"]
    assert annotations(tree.select("#p1").select_all(".ad")) == []


def test_parsing_void_elements():
    assert str(parse_html('<img src="/image.png"/>')) == '<img src="/image.png"/>'
    assert str(parse_html('<img src="/image.png">')) == '<img src="/image.png"/>'


@pytest.mark.parametrize(
    "html",
    [
        "",
        "<body><p>hello, world",
        "<p>hello, world</p></p>",
        "<p>hello, world</div>",
        '<img src="/image.png"></img>',
    ],
)
def test_malformed_html(html):
    with pytest.raises(DOMBuilderException):
        parse_html(html)


def test_tree_walking(tree):
    body = tree.select("body")
    assert body.tag == "body"
    assert isinstance(body.first_child(), TextNode)
    assert isinstance(body.last_child(), TextNode)

    header = body.first_element_child()
    assert header.tag == "header"
    assert isinstance(header.next_sibling(), TextNode)

    div_body = header.next_element_sibling()
    assert div_body.attr("id") == "body"
    assert div_body.attr("title") is None
    assert [
        child.tag for child in div_body.children if isinstance(child, ElementNode)
    ] == ["main", "nav", "aside"]

    main = div_body.first_element_child()
    assert main.tag == "main"
    assert [
        sibling.tag
        for sibling in main.next_siblings()
        if isinstance(sibling, ElementNode)
    ] == ["nav", "aside"]

    aside = div_body.last_element_child()
    assert aside.tag == "aside"
    assert [
        sibling.tag
        for sibling in aside.previous_siblings()
        if isinstance(sibling, ElementNode)
    ] == ["nav", "main"]
    assert isinstance(aside.previous_sibling(), TextNode)

    nav = aside.previous_element_sibling()
    assert nav.tag == "nav"

    div_body = aside.parent
    assert div_body.attr("id") == "body"


def test_root_siblings(tree):
    assert tree.next_sibling() is None
    assert tree.next_element_sibling() is None
    assert tree.next_siblings() == []
    assert tree.previous_sibling() is None
    assert tree.previous_element_sibling() is None
    assert tree.previous_siblings() == []


def test_html(tree):
    sample_html_without_comments = "\n".join(
        re.sub(r"<!-- .* -->", "", line) for line in SAMPLE_HTML.splitlines()
    )
    assert tree.html == sample_html_without_comments
    assert tree.outer_html() == sample_html_without_comments
    m = re.match(r"<html>(?P<inner>.*)</html>", sample_html_without_comments, re.S)
    assert tree.inner_html() == m.group("inner")


def test_lone_text_node(tree):
    text = tree.select("a").first_child()
    assert text.strip() == "Link 1."
    assert text.first_child() is None
    assert text.last_child() is None
    assert text.next_sibling() is None
    assert text.previous_sibling() is None
    assert text.next_element_sibling() is None
    assert text.previous_element_sibling() is None


def test_empty_element(tree):
    div = tree.select('div[data-desc="empty div"]')
    assert div.first_child() is None
    assert div.first_element_child() is None
    assert div.last_child() is None
    assert div.last_element_child() is None
    assert list(div.descendants()) == []


def test_text_content(tree):
    p = tree.select('p[data-desc="escapes"]')
    assert p.text.strip() == "Some escaped characters: &<>\"'"
    assert p.text_content() == p.text


def test_text_mode_comparison():
    t1 = TextNode("abc")
    t2 = TextNode("abc")
    assert t1 == t1
    assert t2 == t2
    assert t1 != t2
    assert t1.text == t2.text


@pytest.mark.parametrize(
    "selector",
    [
        "",
        " ",
        ", p",
        "p, a, ",
        "p > a > ",
        "+ a",
        "[attr=val",
        "[attr=~val]",
        '[attr="val]',
        '[attr="val\\"]',
        "[attr='val]",
        "[attr='val\\']",
        "#id1#id2",
        "th[attr]td",
    ],
)
def test_bad_selector(selector):
    with pytest.raises(SelectorParserException):
        SelectorGroup.from_str(selector)


@pytest.mark.parametrize(
    "selector",
    [
        "td:first-child",
        "td:nth-child(odd)",
        "p::before",
        "p::after",
        "svg|a",
        "*|*",
        "|*",
    ],
)
def test_unsupported_selector(selector):
    with pytest.raises(SelectorParserException):
        SelectorGroup.from_str(selector)


def test_ancestors(tree):
    body = tree.select("body")
    main = tree.select("main")
    assert annotations(main.ancestors()) == ["2.2", "2", None]
    assert annotations(main.ancestors(root=body)) == ["2.2", "2"]
    assert annotations(main.ancestors(root=main)) == []
    with pytest.raises(Exception):
        list(body.ancestors(root=main))
    with pytest.raises(Exception):
        list(main.ancestors(root=tree.select("p")))


def test_node_misc(tree):
    assert tree.query_selector("main").annotation == "2.2.1"
    assert annotations(tree.query_selector_all(".ad")) == [
        "2.2.3.1",
        "2.2.3.2",
        "2.2.3.3",
        "2.2.3.4",
    ]
    assert tree.child_nodes() == tree.children
    assert tree.select(".ad.first-party").classes == ["first-party", "ad"]
    assert tree.select(".ad.first-party").class_list() == ["first-party", "ad"]


def test_selector_misc(tree):
    sel = SelectorGroup.from_str("p, div")
    assert len(sel) == 2
    assert (
        tree.select_all(sel) == tree.select_all("p, div") == tree.select_all("div, p")
    )
    assert tree.select_all(sel[0]) == tree.select_all("p")
