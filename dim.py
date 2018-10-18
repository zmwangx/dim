"""
:mod:`dim` is an HTML parser and simple DOM implementation with CSS
selector support.

:mod:`dim`

- is a single module;
- has no dependency outside `PSL <https://docs.python.org/3/library/>`_;
- is not crazy long;
- supports Python 3.4 and forward,

so the file could be directly embedded in any Python 3.4+ application,
or even in a monolithic source file. :mod:`dim` was designed to ease the
development of `googler(1) <https://github.com/jarun/googler/>`_, which
itself promises to be a single Python script with zero third-party dep.

Simple example:

.. doctest::

   >>> import dim
   >>> html = '''
   ... <html>
   ... <body>
   ...   <table id="primary">
   ...     <thead>
   ...       <tr><th class="bold">A</th><th>B</th></tr>
   ...     </thead>
   ...     <tbody>
   ...       <tr class="highlight"><td class="bold">1</td><td>2</td></tr>
   ...       <tr><td class="bold">3</td><td>4</td></tr>
   ...       <tr><td class="bold">5</td><td>6</td></tr>
   ...       <tr><td class="bold">7</td><td>8</td></tr>
   ...     </tbody>
   ...   </table>
   ...   <table id="secondary">
   ...     <thead>
   ...       <tr><th class="bold">C</th><th>D</th></tr>
   ...     </thead>
   ...     <tbody></tbody>
   ...   </table>
   ... </body>
   ... </html>'''
   >>> root = dim.parse_html(html)
   >>> [elem.text for elem in root.select_all('table#primary th.bold, '
   ...                                        'table#primary tr.highlight + tr > td.bold')]
   ['A', '3']
   >>> [elem.text for elem in root.select_all('table#primary th.bold, '
   ...                                        'table#primary tr.highlight ~ tr > td.bold')]
   ['A', '3', '5', '7']
   >>> [elem.text for elem in root.select_all('th.bold, tr.highlight ~ tr > td.bold')]
   ['A', '3', '5', '7', 'C']
"""

import html
import re
import textwrap
from collections import OrderedDict
from enum import Enum
from html.parser import HTMLParser

try:
    from typing import (
        Any,
        Dict,
        Generator,
        Iterable,
        Iterator,
        List,
        Match,
        Optional,
        Tuple,
        Union,
        cast,
    )
except ImportError:  # pragma: no cover
    # Python 3.4 without external typing module

    class _TypeStub:
        def __getitem__(self, _):  # type: ignore
            return None

    Any = None
    Dict = Generator = Iterable = Iterator = List = Match = _TypeStub()  # type: ignore
    Optional = Tuple = Union = _TypeStub()  # type: ignore

    def cast(typ, val):  # type: ignore
        return val


SelectorGroupLike = Union[str, "SelectorGroup", "Selector"]


class Node(object):
    """
    Represents a DOM node.

    Parts of JavaScript's DOM ``Node`` API and ``Element`` API are
    mirrored here, with extensions. In particular, ``querySelector`` and
    ``querySelectorAll`` are mirrored.

    Notable properties and methods: :meth:`attr()`, :attr:`classes`,
    :attr:`html`, :attr:`text`, :meth:`ancestors()`,
    :meth:`descendants()`, :meth:`select()`, :meth:`select_all()`,
    :meth:`matched_by()`,

    Attributes:
        tag      (:class:`Optional`\\[:class:`str`])
        attrs    (:class:`Dict`\\[:class:`str`, :class:`str`])
        parent   (:class:`Optional`\\[:class:`Node`])
        children (:class:`List`\\[:class:`Node`])
    """

    # Meant to be reimplemented by subclasses.
    def __init__(self) -> None:
        self.tag = None  # type: Optional[str]
        self.attrs = {}  # type: Dict[str, str]
        self.parent = None  # type: Optional[Node]
        self.children = []  # type: List[Node]

        # Used in DOMBuilder.
        self._partial = False

    # HTML representation of the node. Meant to be implemented by
    # subclasses.
    def __str__(self) -> str:  # pragma: no cover
        raise NotImplementedError

    def select(self, selector: SelectorGroupLike) -> Optional["Node"]:
        """DOM ``querySelector`` clone. Returns one match (if any)."""
        selector = self._normalize_selector(selector)
        for node in self._select_all(selector):
            return node
        return None

    def query_selector(self, selector: SelectorGroupLike) -> Optional["Node"]:
        """Alias of :meth:`select`."""
        return self.select(selector)

    def select_all(self, selector: SelectorGroupLike) -> List["Node"]:
        """DOM ``querySelectorAll`` clone. Returns all matches in a list."""
        selector = self._normalize_selector(selector)
        return list(self._select_all(selector))

    def query_selector_all(self, selector: SelectorGroupLike) -> List["Node"]:
        """Alias of :meth:`select_all`."""
        return self.select_all(selector)

    def matched_by(
        self, selector: SelectorGroupLike, root: Optional["Node"] = None
    ) -> bool:
        """
        Checks whether this node is matched by `selector`.

        See :meth:`SelectorGroup.matches()`.
        """
        selector = self._normalize_selector(selector)
        return selector.matches(self, root=root)

    @staticmethod
    def _normalize_selector(selector: SelectorGroupLike) -> "SelectorGroup":
        if isinstance(selector, str):
            return SelectorGroup.from_str(selector)
        if isinstance(selector, SelectorGroup):
            return selector
        if isinstance(selector, Selector):
            return SelectorGroup([selector])
        raise ValueError("not a selector or group of selectors: %s" % repr(selector))

    def _select_all(self, selector: "SelectorGroup") -> Generator["Node", None, None]:
        for descendant in self.descendants():
            if selector.matches(descendant, root=self):
                yield descendant

    def child_nodes(self) -> List["Node"]:
        return self.children

    def first_child(self) -> Optional["Node"]:
        if self.children:
            return self.children[0]
        else:
            return None

    def first_element_child(self) -> Optional["Node"]:
        for child in self.children:
            if isinstance(child, ElementNode):
                return child
        return None

    def last_child(self) -> Optional["Node"]:
        if self.children:
            return self.children[-1]
        else:
            return None

    def last_element_child(self) -> Optional["Node"]:
        for child in reversed(self.children):
            if isinstance(child, ElementNode):
                return child
        return None

    def next_sibling(self) -> Optional["Node"]:
        """.. note:: Not O(1), use with caution."""
        next_siblings = self.next_siblings()
        if next_siblings:
            return next_siblings[0]
        else:
            return None

    def next_siblings(self) -> List["Node"]:
        parent = self.parent
        if not parent:
            return []
        try:
            index = parent.children.index(self)
            return parent.children[index + 1 :]
        except ValueError:  # pragma: no cover
            raise ValueError("node is not found in children of its parent")

    def next_element_sibling(self) -> Optional["ElementNode"]:
        """.. note:: Not O(1), use with caution."""
        for sibling in self.next_siblings():
            if isinstance(sibling, ElementNode):
                return sibling
        return None

    def previous_sibling(self) -> Optional["Node"]:
        """.. note:: Not O(1), use with caution."""
        previous_siblings = self.previous_siblings()
        if previous_siblings:
            return previous_siblings[0]
        else:
            return None

    def previous_siblings(self) -> List["Node"]:
        """
        Compared to the natural DOM order, the order of returned nodes
        are reversed. That is, the adjacent sibling (if any) is the
        first in the returned list.
        """
        parent = self.parent
        if not parent:
            return []
        try:
            index = parent.children.index(self)
            if index > 0:
                return parent.children[index - 1 :: -1]
            else:
                return []
        except ValueError:  # pragma: no cover
            raise ValueError("node is not found in children of its parent")

    def previous_element_sibling(self) -> Optional["ElementNode"]:
        """.. note:: Not O(1), use with caution."""
        for sibling in self.previous_siblings():
            if isinstance(sibling, ElementNode):
                return sibling
        return None

    def ancestors(
        self, *, root: Optional["Node"] = None
    ) -> Generator["Node", None, None]:
        """
        Ancestors are generated in reverse order of depth, stopping at
        `root`.

        A :class:`RuntimeException` is raised if `root` is not in the
        ancestral chain.
        """
        if self is root:
            return
        ancestor = self.parent
        while ancestor is not root:
            if ancestor is None:
                raise RuntimeError("provided root node not found in ancestral chain")
            yield ancestor
            ancestor = ancestor.parent
        if root:
            yield root

    def descendants(self) -> Generator["Node", None, None]:
        """Descendants are generated in depth-first order."""
        for child in self.children:
            yield child
            yield from child.descendants()

    def attr(self, attr: str) -> Optional[str]:
        """Returns the attribute if it exists on the node, otherwise ``None``."""
        return self.attrs.get(attr)

    @property
    def html(self) -> str:
        """
        HTML representation of the node.

        (For a :class:`TextNode`, :meth:`html` returns the escaped version of the
        text.
        """
        return str(self)

    def outer_html(self) -> str:
        """Alias of :attr:`html`."""
        return self.html

    def inner_html(self) -> str:
        """HTML representation of the node's children."""
        return "".join(child.html for child in self.children)

    @property
    def text(self) -> str:  # pragma: no cover
        """This property is expected to be implemented by subclasses."""
        raise NotImplementedError

    def text_content(self) -> str:
        """Alias of :attr:`text`."""
        return self.text

    @property
    def classes(self) -> List[str]:
        return self.attrs.get("class", "").split()

    def class_list(self) -> List[str]:
        return self.classes


class ElementNode(Node):
    """
    Represents an element node.

    Note that tag and attribute names are case-insensitive; attribute
    values are case-sensitive.
    """

    def __init__(
        self,
        tag: str,
        attrs: Iterable[Tuple[str, str]],
        *,
        parent: Optional["Node"] = None,
        children: Optional[List["Node"]] = None
    ) -> None:
        Node.__init__(self)
        self.tag = tag.lower()  # type: str
        self.attrs = OrderedDict((attr.lower(), val) for attr, val in attrs)
        self.parent = parent
        self.children = children or []

    def __repr__(self) -> str:
        s = "<" + self.tag
        if self.attrs:
            s += " attrs=%s" % repr(list(self.attrs.items()))
        if self.children:
            s += " children=%s" % repr(self.children)
        s += ">"
        return s

    # https://ipython.readthedocs.io/en/stable/api/generated/IPython.lib.pretty.html
    def _repr_pretty_(self, p: Any, cycle: bool) -> None:  # pragma: no cover
        if cycle:
            raise RuntimeError("cycle detected in DOM tree")
        p.text("<\x1b[1m%s\x1b[0m" % self.tag)
        if self.attrs:
            p.text(" attrs=%s" % repr(list(self.attrs.items())))
        if self.children:
            p.text(" children=[")
            if len(self.children) == 1 and isinstance(self.first_child(), TextNode):
                p.text("\x1b[4m%s\x1b[0m" % repr(self.first_child()))
            else:
                with p.indent(2):
                    for child in self.children:
                        p.break_()
                        if hasattr(child, "_repr_pretty_"):
                            child._repr_pretty_(p, False)  # type: ignore
                        else:
                            p.text("\x1b[4m%s\x1b[0m" % repr(child))
                        p.text(",")
                p.break_()
            p.text("]")
        p.text(">")

    def __str__(self) -> str:
        """HTML representation of the node."""
        s = "<" + self.tag
        for attr, val in self.attrs.items():
            s += ' %s="%s"' % (attr, html.escape(val))
        if self.children:
            s += ">"
            s += "".join(str(child) for child in self.children)
            s += "</%s>" % self.tag
        else:
            if _tag_is_void(self.tag):
                s += "/>"
            else:
                s += "></%s>" % self.tag
        return s

    @property
    def text(self) -> str:
        """The concatenation of all descendant text nodes."""
        return "".join(child.text for child in self.children)


class TextNode(str, Node):
    """
    Represents a text node.

    Subclasses :class:`Node` and :class:`str`.
    """

    def __new__(cls, text: str) -> "TextNode":
        s = str.__new__(cls, text)  # type: ignore
        s.parent = None
        return s  # type: ignore

    def __init__(self, text: str) -> None:
        Node.__init__(self)

    def __repr__(self) -> str:
        return "<%s>" % str.__repr__(self)

    # HTML-escaped form of the text node. use text() for unescaped
    # version.
    def __str__(self) -> str:
        return html.escape(self)

    def __eq__(self, other: object) -> bool:
        """
        Two text nodes are equal if and only if they are the same node.

        For string comparision, use :attr:`text`.
        """
        return self is other

    def __ne__(self, other: object) -> bool:
        """
        Two text nodes are non-equal if they are not the same node.

        For string comparision, use :attr:`text`.
        """
        return self is not other

    @property
    def text(self) -> str:
        return str.__str__(self)


class DOMBuilderException(Exception):
    """
    Exception raised when :class:`DOMBuilder` detects a bad state.

    Attributes:
        pos (:class:`Tuple`\\[:class:`int`, :class:`int`]):
            Line number and offset in HTML input.
        why (:class:`str`):
            Reason of the exception.
    """

    def __init__(self, pos: Tuple[int, int], why: str) -> None:
        self.pos = pos
        self.why = why

    def __str__(self) -> str:  # pragma: no cover
        return "DOM builder aborted at %d:%d: %s" % (self.pos[0], self.pos[1], self.why)


class DOMBuilder(HTMLParser):
    """
    HTML parser / DOM builder.

    Subclasses :class:`html.parser.HTMLParser`.

    Consume HTML and builds a :class:`Node` tree. Once finished, use
    :attr:`root` to access the root of the tree.

    This parser cannot parse malformed HTML with tag mismatch.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack = []  # type: List[Node]

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, str]]) -> None:
        node = ElementNode(tag, attrs)
        node._partial = True
        self._stack.append(node)
        # For void elements, immediately invoke the end tag handler (see
        # handle_startendtag()).
        if _tag_is_void(tag):
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        children = []
        while self._stack and not self._stack[-1]._partial:
            children.append(self._stack.pop())
        if not self._stack:
            raise DOMBuilderException(self.getpos(), "extra end tag: %s" % repr(tag))
        parent = self._stack[-1]
        if parent.tag != tag:
            raise DOMBuilderException(
                self.getpos(),
                "expecting end tag %s, got %s" % (repr(parent.tag), repr(tag)),
            )
        parent.children = list(reversed(children))
        parent._partial = False
        for child in children:
            child.parent = parent

    # Make parser behavior for explicitly and implicitly void elements
    # (e.g., <hr> vs <hr/>) consistent. The former triggers
    # handle_starttag only, whereas the latter triggers
    # handle_startendtag (which by default triggers both handle_starttag
    # and handle_endtag). See https://www.bugs.python.org/issue25258.
    def handle_startendtag(self, tag: str, attrs: List[Tuple[str, str]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_data(self, text: str) -> None:
        if not self._stack:
            # Ignore text nodes before the first tag.
            return
        self._stack.append(TextNode(text))

    @property
    def root(self) -> "Node":
        """
        Finishes processing and returns the root node.

        Raises :class:`DOMBuilderException` if there is no root tag or
        root tag is not closed yet.
        """
        if not self._stack:
            raise DOMBuilderException(self.getpos(), "no root tag")
        if self._stack[0]._partial:
            raise DOMBuilderException(self.getpos(), "root tag not closed yet")
        return self._stack[0]


def parse_html(html: str, *, ParserClass: type = DOMBuilder) -> "Node":
    """
    Parses HTML string, builds DOM, and returns root node.

    The parser may raise :class:`DOMBuilderException`.

    Args:
        html: input HTML string
        ParserClass: :class:`DOMBuilder` or a subclass

    Returns:
        Root note of the parsed tree. If the HTML string contains
        multiple top-level elements, only the first is returned and the
        rest are lost.
    """
    builder = ParserClass()  # type: DOMBuilder
    builder.feed(html)
    builder.close()
    return builder.root


class SelectorParserException(Exception):
    """
    Exception raised when the selector parser fails to parse an input.

    Attributes:
        s (:class:`str`):
            The input string to be parsed.
        cursor (:class:`int`):
            Cursor position where the failure occurred.
        why (:class:`str`):
            Reason of the failure.
    """

    def __init__(self, s: str, cursor: int, why: str) -> None:
        self.s = s
        self.cursor = cursor
        self.why = why

    def __str__(self) -> str:  # pragma: no cover
        return "selector parser aborted at character %d of %s: %s" % (
            self.cursor,
            repr(self.s),
            self.why,
        )


class SelectorGroup:
    """
    Represents a group of CSS selectors.

    A group of CSS selectors is simply a comma-separated list of
    selectors. [#]_ See :class:`Selector` documentation for the scope of
    support.

    Typically, a :class:`SelectorGroup` is constructed from a string
    (e.g., ``th.center, td.center``) using the factory function
    :meth:`from_str`.

    .. [#] https://www.w3.org/TR/selectors-3/#grouping
    """

    def __init__(self, selectors: Iterable["Selector"]) -> None:
        self._selectors = list(selectors)

    def __repr__(self) -> str:
        return "<SelectorGroup %s>" % repr(str(self))

    def __str__(self) -> str:
        return ", ".join(str(selector) for selector in self._selectors)

    def __len__(self) -> int:
        return len(self._selectors)

    def __getitem__(self, index: int) -> "Selector":
        return self._selectors[index]

    def __iter__(self) -> Iterator["Selector"]:
        return iter(self._selectors)

    @classmethod
    def from_str(cls, s: str) -> "SelectorGroup":
        """
        Parses input string into a group of selectors.

        :class:`SelectorParserException` is raised on invalid input. See
        :class:`Selector` documentation for the scope of support.

        Args:
            s: input string

        Returns:
            Parsed group of selectors.
        """
        i = 0
        selectors = []
        while i < len(s):
            selector, i = Selector.from_str(s, i)
            selectors.append(selector)
        if not selectors:
            raise SelectorParserException(s, i, "selector group is empty")
        return cls(selectors)

    def matches(self, node: "Node", root: Optional["Node"] = None) -> bool:
        """
        Decides whether the group of selectors matches `node`.

        The group of selectors matches `node` as long as one of the
        selectors matches `node`.

        If `root` is provided and child and/or descendant combinators
        are involved, parent/ancestor lookup terminates at `root`.
        """
        return any(selector.matches(node, root=root) for selector in self)


class Selector:
    """
    Represents a CSS selector.

    Recall that a CSS selector is a chain of one or more *sequences of
    simple selectors* separated by *combinators*. [#selectors-3]_ This
    concept is represented as a cons list of sequences of simple
    selectors (in right to left order). This class in fact holds a
    single sequence, with an optional combinator and reference to the
    previous sequence.

    For instance, ``main#main p.important.definition >
    a.term[id][href]`` would be parsed into (schematically) the
    following structure::

        ">" tag='a' classes=('term') attrs=([id], [href]) ~>
        " " tag='p' classes=('important', 'definition') ~>
        tag='main' id='main'

    Each line is held in a separate instance of :class:`Selector`,
    linked together by the :attr:`previous` attribute.

    Supported grammar (from selectors level 3 [#selectors-3]_):

    - Type selectors;
    - Universal selectors;
    - Class selectors;
    - ID selectors;
    - Attribute selectors;
    - Combinators.

    Unsupported grammar:

    - Pseudo-classes;
    - Pseudo-elements;
    - Namespace prefixes (``ns|``, ``*|``, ``|``) in any part of any
      selector.

    Rationale:

    - Pseudo-classes have too many variants, a few of which even
      complete with an admittedly not-so-complex minilanguage. These add
      up to a lot of code.
    - Pseudo-elements are useless outside rendering contexts, hence out of
      scope.
    - Namespace support is too niche to be worth the parsing headache.
      *Using namespace prefixes may confuse the parser!*

    Note that the parser only loosely follows the spec and priotizes
    ease of parsing (which includes readability and *writability* of
    regexes), so some invalid selectors may be accepted (in fact, false
    positives abound, but accepting valid inputs is a much more
    important goal than rejecting invalid inputs for this library), and
    some valid selectors may be rejected (but as long as you stick to
    the scope outlined above and common sense you should be fine; the
    false negatives shouldn't be used by actual human beings anyway).

    In particular, whitespace character is simplified to ``\\s`` (ASCII
    mode) despite CSS spec not counting U+000B (VT) as whitespace,
    identifiers are simplified to ``[\\w-]+`` (ASCII mode), and strings
    (attribute selector values can be either identifiers or strings)
    allow escaped quotes (i.e., ``\\'`` inside single-quoted strings and
    ``\\"`` inside double-quoted strings) but everything else is
    interpreted literally. The exact specs for CSS identifiers and
    strings can be found at [#]_.

    Certain selectors and combinators may be implemented in the parser
    but not implemented in matching and/or selection APIs.

    .. [#selectors-3] https://www.w3.org/TR/selectors-3/
    .. [#] https://www.w3.org/TR/CSS21/syndata.html

    Attributes:
        tag (:class:`Optional`\\[:class:`str`]):
            Type selector.
        classes (:class:`List`\\[:class:`str`]):
            Class selectors.
        id (:class:`Optional`\\[:class:`str`]):
            ID selector.
        attrs (:class:`List`\\[:class:`AttributeSelector`]):
            Attribute selectors.
        combinator (:class:`Optional`\\[:class:`Combinator`]):
            Combinator with the previous sequence of simple selectors in
            chain.
        previous (:class:`Optional`\\[:class:`Selector`]):
            Reference to the previous sequence of simple selectors in
            chain.

    """

    def __init__(
        self,
        *,
        tag: Optional[str] = None,
        classes: Optional[List[str]] = None,
        id: Optional[str] = None,
        attrs: Optional[List["AttributeSelector"]] = None,
        combinator: Optional["Combinator"] = None,
        previous: Optional["Selector"] = None
    ) -> None:
        self.tag = tag.lower() if tag else None
        self.classes = classes or []
        self.id = id
        self.attrs = attrs or []
        self.combinator = combinator
        self.previous = previous

    def __repr__(self) -> str:
        return "<Selector %s>" % repr(str(self))

    def __str__(self) -> str:
        sequences = []
        delimiters = []
        seq = self
        while True:
            sequences.append(seq._sequence_str_())
            if seq.previous:
                if seq.combinator == Combinator.DESCENDANT:
                    delimiters.append(" ")
                elif seq.combinator == Combinator.CHILD:
                    delimiters.append(" > ")
                elif seq.combinator == Combinator.NEXT_SIBLING:
                    delimiters.append(" + ")
                elif seq.combinator == Combinator.SUBSEQUENT_SIBLING:
                    delimiters.append(" ~ ")
                else:  # pragma: no cover
                    raise RuntimeError(
                        "unimplemented combinator: %s" % repr(self.combinator)
                    )
                seq = seq.previous
            else:
                delimiters.append("")
                break
        return "".join(
            delimiter + sequence
            for delimiter, sequence in zip(reversed(delimiters), reversed(sequences))
        )

    # Format a single sequence of simple selectors, without combinator.
    def _sequence_str_(self) -> str:
        s = ""
        if self.tag:
            s += self.tag
        if self.classes:
            s += "".join(".%s" % class_ for class_ in self.classes)
        if self.id:
            s += "#%s" % self.id
        if self.attrs:
            s += "".join(str(attr) for attr in self.attrs)
        return s if s else "*"

    @classmethod
    def from_str(cls, s: str, cursor: int = 0) -> Tuple["Selector", int]:
        """
        Parses input string into selector.

        This factory function only parses out one selector (up to a
        comma or EOS), so partial consumption is allowed --- an optional
        `cursor` is taken as input (0 by default) and the moved cursor
        (either after the comma or at EOS) is returned as part of the
        output.

        :class:`SelectorParserException` is raised on invalid input. See
        :class:`Selector` documentation for the scope of support.

        If you need to completely consume a string representing
        (potentially) a group of selectors, use
        :meth:`SelectorGroup.from_str()`.

        Args:
            s:      input string
            cursor: initial cursor position on `s`

        Returns:
            A tuple containing the parsed selector and the moved the
            cursor (either after a comma-delimiter, or at EOS).
        """
        # Simple selectors.
        TYPE_SEL = re.compile(r"[\w-]+", re.A)
        UNIVERSAL_SEL = re.compile(r"\*")
        ATTR_SEL = re.compile(
            r"""\[
            \s*(?P<attr>[\w-]+)\s*
            (
                (?P<op>[~|^$*]?=)\s*
                (
                    (?P<val_identifier>[\w-]+)|
                    (?P<val_string>
                        (?P<quote>['"])
                        (?P<val_string_inner>.*?)
                        (?<!\\)(?P=quote)
                    )
                )\s*
            )?
            \]""",
            re.A | re.X,
        )
        CLASS_SEL = re.compile(r"\.([\w-]+)", re.A)
        ID_SEL = re.compile(r"#([\w-]+)", re.A)
        PSEUDO_CLASS_SEL = re.compile(r":[\w-]+(\([^)]+\))?", re.A)
        PSEUDO_ELEM_SEL = re.compile(r"::[\w-]+", re.A)

        # Combinators
        DESCENDANT_COM = re.compile(r"\s+")
        CHILD_COM = re.compile(r"\s*>\s*")
        NEXT_SIB_COM = re.compile(r"\s*\+\s*")
        SUB_SIB_COM = re.compile(r"\s*~\s*")

        # Misc
        WHITESPACE = re.compile(r"\s*")
        END_OF_SELECTOR = re.compile(r"\s*($|,)")

        tag = None
        classes = []
        id = None
        attrs = []
        combinator = None

        selector = None
        previous_combinator = None

        i = cursor

        # Skip leading whitespace
        m = WHITESPACE.match(s, i)
        if m:
            i = m.end()

        while i < len(s):
            # Parse one simple selector.
            #
            # PEP 572 (assignment expressions; the one that burned Guido
            # so much that he resigned as BDFL) would have been nice; it
            # would have saved us from all the regex match
            # reassignments, and worse still, the casts, since mypy
            # complains about getting Optional[Match[str]] instead of
            # Match[str].
            if TYPE_SEL.match(s, i):
                if tag:
                    raise SelectorParserException(s, i, "multiple type selectors found")
                m = cast(Match[str], TYPE_SEL.match(s, i))
                tag = m.group()
            elif UNIVERSAL_SEL.match(s, i):
                m = cast(Match[str], UNIVERSAL_SEL.match(s, i))
            elif ATTR_SEL.match(s, i):
                m = cast(Match[str], ATTR_SEL.match(s, i))

                attr = m.group("attr")
                op = m.group("op")
                val_identifier = m.group("val_identifier")
                quote = m.group("quote")
                val_string_inner = m.group("val_string_inner")
                if val_identifier is not None:
                    val = val_identifier
                elif val_string_inner is not None:
                    val = val_string_inner.replace("\\" + quote, quote)
                else:
                    val = None

                if op is None:
                    type = AttributeSelectorType.BARE
                elif op == "=":
                    type = AttributeSelectorType.EQUAL
                elif op == "~=":
                    type = AttributeSelectorType.TILDE
                elif op == "|=":
                    type = AttributeSelectorType.PIPE
                elif op == "^=":
                    type = AttributeSelectorType.CARET
                elif op == "$=":
                    type = AttributeSelectorType.DOLLAR
                elif op == "*=":
                    type = AttributeSelectorType.ASTERISK
                else:  # pragma: no cover
                    raise SelectorParserException(
                        s,
                        i,
                        "unrecognized operator %s in attribute selector" % repr(op),
                    )

                attrs.append(AttributeSelector(attr, val, type))
            elif CLASS_SEL.match(s, i):
                m = cast(Match[str], CLASS_SEL.match(s, i))
                classes.append(m.group(1))
            elif ID_SEL.match(s, i):
                if id:
                    raise SelectorParserException(s, i, "multiple id selectors found")
                m = cast(Match[str], ID_SEL.match(s, i))
                id = m.group(1)
            elif PSEUDO_CLASS_SEL.match(s, i):
                raise SelectorParserException(s, i, "pseudo-classes not supported")
            elif PSEUDO_ELEM_SEL.match(s, i):
                raise SelectorParserException(s, i, "pseudo-elements not supported")
            else:
                raise SelectorParserException(
                    s, i, "expecting simple selector, found none"
                )
            i = m.end()

            # Try to parse a combinator, or end the selector.
            if CHILD_COM.match(s, i):
                m = cast(Match[str], CHILD_COM.match(s, i))
                combinator = Combinator.CHILD
            elif NEXT_SIB_COM.match(s, i):
                m = cast(Match[str], NEXT_SIB_COM.match(s, i))
                combinator = Combinator.NEXT_SIBLING
            elif SUB_SIB_COM.match(s, i):
                m = cast(Match[str], SUB_SIB_COM.match(s, i))
                combinator = Combinator.SUBSEQUENT_SIBLING
            elif END_OF_SELECTOR.match(s, i):
                m = cast(Match[str], END_OF_SELECTOR.match(s, i))
                combinator = None
            # Need to parse descendant combinator at the very end
            # because it could be a prefix to all previous cases.
            elif DESCENDANT_COM.match(s, i):
                m = cast(Match[str], DESCENDANT_COM.match(s, i))
                combinator = Combinator.DESCENDANT
            else:
                continue
            i = m.end()

            if combinator and i == len(s):
                raise SelectorParserException(s, i, "unexpected end at combinator")

            selector = cls(
                tag=tag,
                classes=classes,
                id=id,
                attrs=attrs,
                combinator=previous_combinator,
                previous=selector,
            )
            previous_combinator = combinator

            # End of selector.
            if combinator is None:
                break

            tag = None
            classes = []
            id = None
            attrs = []
            combinator = None

        if not selector:
            raise SelectorParserException(s, i, "selector is empty")

        return selector, i

    def matches(self, node: "Node", root: Optional["Node"] = None) -> bool:
        """
        Decides whether the selector matches `node`.

        Each sequence of simple selectors in the selector's chain must
        be matched for a positive.

        If `root` is provided and child and/or descendant combinators
        are involved, parent/ancestor lookup terminates at `root`.
        """
        if self.tag:
            if not node.tag or node.tag != self.tag:
                return False
        if self.id:
            if node.attrs.get("id") != self.id:
                return False
        if self.classes:
            classes = node.classes
            for class_ in self.classes:
                if class_ not in classes:
                    return False
        if self.attrs:
            for attr_selector in self.attrs:
                if not attr_selector.matches(node):
                    return False

        if not self.previous:
            return True

        if self.combinator == Combinator.DESCENDANT:
            return any(
                self.previous.matches(ancestor, root=root)
                for ancestor in node.ancestors()
            )
        elif self.combinator == Combinator.CHILD:
            if node is root or node.parent is None:
                return False
            else:
                return self.previous.matches(node.parent)
        elif self.combinator == Combinator.NEXT_SIBLING:
            sibling = node.previous_element_sibling()
            if not sibling:
                return False
            else:
                return self.previous.matches(sibling)
        elif self.combinator == Combinator.SUBSEQUENT_SIBLING:
            return any(
                self.previous.matches(sibling, root=root)
                for sibling in node.previous_siblings()
                if isinstance(sibling, ElementNode)
            )
        else:  # pragma: no cover
            raise RuntimeError("unimplemented combinator: %s" % repr(self.combinator))


class AttributeSelector:
    """
    Represents an attribute selector.

    Attributes:
        attr (:class:`str`)
        val  (:class:`Optional`\\[:class:`str`])
        type (:class:`AttributeSelectorType`)
    """

    def __init__(
        self, attr: str, val: Optional[str], type: "AttributeSelectorType"
    ) -> None:
        self.attr = attr.lower()
        self.val = val
        self.type = type

    def __repr__(self) -> str:
        return "<AttributeSelector %s>" % repr(str(self))

    def __str__(self) -> str:
        if self.type == AttributeSelectorType.BARE:
            fmt = "[{attr}{val:.0}]"
        elif self.type == AttributeSelectorType.EQUAL:
            fmt = "[{attr}={val}]"
        elif self.type == AttributeSelectorType.TILDE:
            fmt = "[{attr}~={val}]"
        elif self.type == AttributeSelectorType.PIPE:
            fmt = "[{attr}|={val}]"
        elif self.type == AttributeSelectorType.CARET:
            fmt = "[{attr}^={val}]"
        elif self.type == AttributeSelectorType.DOLLAR:
            fmt = "[{attr}$={val}]"
        elif self.type == AttributeSelectorType.ASTERISK:
            fmt = "[{attr}*={val}]"
        return fmt.format(attr=self.attr, val=repr(self.val))

    def matches(self, node: "Node") -> bool:
        val = node.attrs.get(self.attr)
        if val is None:
            return False
        if self.type == AttributeSelectorType.BARE:
            return True
        elif self.type == AttributeSelectorType.EQUAL:
            return val == self.val
        elif self.type == AttributeSelectorType.TILDE:
            return self.val in val.split()
        elif self.type == AttributeSelectorType.PIPE:
            return val == self.val or val.startswith("%s-" % self.val)
        elif self.type == AttributeSelectorType.CARET:
            return bool(self.val and val.startswith(self.val))
        elif self.type == AttributeSelectorType.DOLLAR:
            return bool(self.val and val.endswith(self.val))
        elif self.type == AttributeSelectorType.ASTERISK:
            return bool(self.val and self.val in val)
        else:  # pragma: no cover
            raise RuntimeError("unimplemented attribute selector: %s" % repr(self.type))


# Enum: basis for poor man's algebraic data type.
class AttributeSelectorType(Enum):
    """
    Attribute selector types.

    Members correspond to the following forms of attribute selector:

    - :attr:`BARE`: ``[attr]``;
    - :attr:`EQUAL`: ``[attr=val]``;
    - :attr:`TILDE`: ``[attr~=val]``;
    - :attr:`PIPE`: ``[attr|=val]``;
    - :attr:`CARET`: ``[attr^=val]``;
    - :attr:`DOLLAR`: ``[attr$=val]``;
    - :attr:`ASTERISK`: ``[attr*=val]``.
    """

    # [attr]
    BARE = 1
    # [attr=val]
    EQUAL = 2
    # [attr~=val]
    TILDE = 3
    # [attr|=val]
    PIPE = 4
    # [attr^=val]
    CARET = 5
    # [attr$=val]
    DOLLAR = 6
    # [attr*=val]
    ASTERISK = 7


class Combinator(Enum):
    """
    Combinator types.

    Members correspond to the following combinators:

    - :attr:`DESCENDANT`: ``A B``;
    - :attr:`CHILD`: ``A > B``;
    - :attr:`NEXT_SIBLING`: ``A + B``;
    - :attr:`SUBSEQUENT_SIBLING`: ``A ~ B``.
    """

    # ' '
    DESCENDANT = 1
    # >
    CHILD = 2
    # +
    NEXT_SIBLING = 3
    # ~
    SUBSEQUENT_SIBLING = 4


def _tag_is_void(tag: str) -> bool:
    """
    Checks whether the tag corresponds to a void element.

    https://www.w3.org/TR/html5/syntax.html#void-elements
    https://html.spec.whatwg.org/multipage/syntax.html#void-elements
    """
    return tag.lower() in (
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    )
