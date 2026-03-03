import os
import sys
sys.path.insert(0, os.path.abspath('../../src'))
import maptrix

project = 'maptrix'
copyright = '2026, Aman Ranjan'
author = 'Aman Ranjan'
release = 'v'+maptrix.__version__

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    # 'sphinx.ext.viewcode',
    'sphinx_autodoc_typehints',
    'myst_parser'
]

napoleon_google_docstring = True
napoleon_numpy_docstring = False
html_copy_source = False
html_show_sourcelink = False


templates_path = ['_templates']
exclude_patterns = []

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']
