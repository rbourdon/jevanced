"""jevanced: lets the Jev decision model drive an Ultima Online character
through Razor Enhanced.

Everything in this package runs under IronPython 3.4 (Razor Enhanced's
script engine) and CPython 3 (for tests). Only ``jevanced.razor.adapter``
talks to the Razor Enhanced API, and only ``jevanced.ui.winforms`` and
``jevanced.keystore``'s DPAPI helper touch .NET.
"""

__version__ = "0.1.0"
