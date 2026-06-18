# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'TensorBrain'
copyright = '2024, Imvision'
author = 'Imvision'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'breathe',
    'myst_parser',
]

source_suffix = {
    '.rst': 'restructuredtext',
    '.md': 'markdown',
}

exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

root_doc = 'index'
language = 'zh_CN'

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

pygments_style = 'sphinx'
html_theme = 'sphinx_rtd_theme'
html_show_sourcelink = False

html_static_path = ['_static']  # 确保你的项目有 _static 文件夹
html_css_files = ['custom.css']  # 引入你的 CSS 文件

# doxygen config
breathe_projects = {"myproject": "../../out/xml"}
breathe_default_project = "myproject"

