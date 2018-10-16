:mod:`dim`
==============

.. TODO: add appropriate documentation to each section.

.. image:: _static/download-dim.py-brightgreen.svg
   :target: https://raw.githubusercontent.com/zmwangx/dim/master/dim.py

.. automodule:: dim
   :no-members:

.. autosummary::
   :nosignatures:

   dim.parse_html
   dim.DOMBuilder
   dim.Node
   dim.ElementNode
   dim.TextNode
   dim.SelectorGroup
   dim.Selector
   dim.AttributeSelector
   dim.AttributeSelectorType
   dim.Combinator
   dim.DOMBuilderException
   dim.SelectorParserException

Parsing HTML and building DOM
-----------------------------

.. autofunction:: dim.parse_html
.. autoclass:: dim.DOMBuilder

Nodes and elements
------------------

The DOM implementation is exposed through the :class:`Node` API. There are only
two types of :class:`Node`'s in this implementation: :class:`ElementNode` and
:class:`TextNode` (both subclasses :class:`Node` and supports the full API).

The base class :class:`Node` should not be manually instantiated; use
:func:`parse_html` or :class:`DOMBuilder`. :class:`ElementNode` and
:class:`TextNode` may be manually instantiated (though not recommended).

.. autoclass:: dim.Node
.. autoclass:: dim.ElementNode
.. autoclass:: dim.TextNode
   :special-members: __eq__, __ne__

CSS selectors
-------------

CSS querying support is implemented mainly through two classes:
:class:`Selector` and :class:`SelectorGroup`. Both classes have a factory
function named ``from_str()`` to parse string representations, although one may
directly use selector (group) strings with the :class:`Node` API (notably with
:meth:`Node.select()`, :meth:`Node.select_all()`, and :meth:`Node.matched_by()`)
and avoid explicitly constructing objects altogether.

.. autoclass:: dim.SelectorGroup
   :special-members: __len__, __getitem__, __iter__
.. autoclass:: dim.Selector
.. autoclass:: dim.AttributeSelector
.. autoclass:: dim.AttributeSelectorType
.. autoclass:: dim.Combinator

Exceptions
----------

.. autoclass:: dim.DOMBuilderException
.. autoclass:: dim.SelectorParserException
