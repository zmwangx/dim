import datetime
import os
import sys

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath(".."))

import genparamdoc
import dim

def copyright_years():
    this_year = datetime.date.today().year
    if this_year == 2018:
        return str(this_year)
    else:
        return "2018\u2013%s" % this_year

project = "dim"
copyright = "%s, Zhiming Wang" % copyright_years()
author = "Zhiming Wang"
version = "dev"
release = "dev"
master_doc = "index"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "genparamdoc",
    "sphinx.ext.napoleon",
    "sphinx_autodoc_typehints",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx.ext.doctest",
]

# autodoc
autodoc_default_flags = ["members", "undoc-members"]
autodoc_member_order = "bysource"

# intersphinx
intersphinx_mapping = {'python': ('https://docs.python.org/3', None)}

# html
html_theme = "python_docs_theme"
html_last_updated_fmt = "%b %d, %Y"
html_sidebars = {"**": ["localtoc.html", "sourcelink.html"]}
html_theme_options = {"collapsiblesidebar": True}
