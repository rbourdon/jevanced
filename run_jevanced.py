"""Razor Enhanced entry point for jevanced.

In Razor Enhanced: Scripting tab > Add > pick this file > Play.
It must sit next to the ``jevanced`` folder (both go in Razor Enhanced's
Scripts folder). Pressing Stop in Razor Enhanced also stops jevanced.
"""

import os
import sys


def _jevanced_home():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        pass
    try:
        return Misc.CurrentScriptDirectory()  # noqa: F821 (Razor Enhanced global)
    except Exception:
        return os.getcwd()


_home = _jevanced_home()
if _home not in sys.path:
    sys.path.insert(0, _home)

# Razor Enhanced keeps imported modules between runs; drop ours so an
# updated copy of jevanced is picked up without restarting the client.
for _name in list(sys.modules):
    if _name == "jevanced" or _name.startswith("jevanced."):
        del sys.modules[_name]

from jevanced.app import build_app  # noqa: E402
from jevanced.razor.adapter import RazorAdapter, RazorApi  # noqa: E402
from jevanced.ui.winforms import start_window  # noqa: E402

# These names are Razor Enhanced's API objects, injected into this script.
# They're handed to the adapter, the only module that calls them.
_api = RazorApi(
    Player=Player,  # noqa: F821
    Mobiles=Mobiles,  # noqa: F821
    Items=Items,  # noqa: F821
    Target=Target,  # noqa: F821
    Spells=Spells,  # noqa: F821
    Journal=Journal,  # noqa: F821
    Misc=Misc,  # noqa: F821
    Statics=Statics,  # noqa: F821
)
_app = build_app(RazorAdapter(_api))
_window = start_window(_app)
try:
    _app.serve()
finally:
    _app.request_shutdown()
    _window.close()
