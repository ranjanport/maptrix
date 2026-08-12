import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
import maptrix

project = 'maptrix'
copyright = '2026, Aman Ranjan'
author = 'Aman Ranjan'
release = 'v'+maptrix.__version__

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    # 'sphinx.ext.viewcode',
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
