# jevanced

jevanced lets **Jev**, Typesafe's decision model, drive an Ultima Online
character through [Razor Enhanced](https://github.com/RazorEnhanced/RazorEnhanced)
instead of hand-written macros. Each turn it reads the game state through
Razor Enhanced, lists the moves that make sense (bandage, step away from a
monster, wait), asks Jev which one to take, and carries it out. It never
starts a fight: there is no attack action.
A small window lets you enter your Jev API key, start and stop, and watch
what it's doing.

## Status

- **Run in a test client, not yet on Windows.** Razor Enhanced 1.0.0.14 in
  ClassicUO, against a private local ModernUO shard, running under Wine. The
  window, key storage, dry run, the STOP button and every action (walk,
  path-to, war mode, skills, items with a target, speech) worked
  there. CI also runs on Windows: it installs with `install.ps1`, runs the
  tests on IronPython for .NET Framework (Razor Enhanced's engine), and
  drives the real window and DPAPI key storage (`tools/windows_smoke.py`).
  It still needs a player to run it in the game on Windows before it's
  called working.
- **Talking to Jev.** jevanced calls Typesafe's System One API
  ([docs](https://docs.typesafe.ai/api)). Jev doesn't invent actions: it
  picks one of the options jevanced offers and says how sure it is. In the
  test client Jev bandaged when hurt and stepped away from an orc that came
  close. That test character was a staff character with maxed stats, so it
  says nothing about how a new character would fare. An offline stub that only bandages is still there for
  trying jevanced without a key (set `"backend": "stub"` in
  `settings.json`).
- **Known gaps.** Razor Enhanced only learns other creatures' health when
  the shard sends it, so Jev may see a wounded monster as unhurt. For now
  jevanced only keeps a character alive; it doesn't do a task such as
  lumberjacking yet.

## Install

In PowerShell on the computer you play on, run:

```
irm https://raw.githubusercontent.com/rbourdon/jevanced/main/install.ps1 | iex
```

It finds Razor Enhanced, downloads the latest release and puts it in Razor
Enhanced's `Scripts` folder. Run the same line again to update. Then, in
Razor Enhanced: **Scripting** tab > **Add** > `run_jevanced.py` > **Play**.

If you'd rather do it by hand, download `jevanced.zip` from the
[latest release](https://github.com/rbourdon/jevanced/releases/latest) and
unzip it into Razor Enhanced's `Scripts` folder.

Needs Razor Enhanced 0.8 or later (its scripts run on IronPython 3.4).

## Use

1. Paste your Jev API key and press **Save key**. The key is encrypted
   with Windows DPAPI for your Windows account and saved in
   `%APPDATA%\jevanced\jev_key.bin`. It is never logged or shown in full;
   the window shows only its last four characters.
2. Leave **Dry run** on for a first try: jevanced logs what it would do
   without doing it.
3. Press **Start**. The key is checked with Jev first; if it's missing or
   rejected, the window says so and nothing runs.
4. Press **STOP** at any time. It is the kill switch: the loop stops before
   its next action, including an action Jev has already chosen.

Settings are saved in `%APPDATA%\jevanced\settings.json` and the activity
log in `%APPDATA%\jevanced\jevanced.log`.

## Safety

- **Kill switch.** The STOP button is always at the top of the window, and
  the window stays on top of the client by default. Pressing Stop on the
  script in Razor Enhanced also stops jevanced, as does closing the window.
- **Automatic stops.** jevanced stops on its own when the character dies,
  the client disconnects, Jev rejects the key, or several ticks in a row
  fail.
- **Only known actions.** Jev's reply is validated against a fixed list of
  actions (`jevanced/actions.py`) with bounded values. Anything else is
  ignored and logged. Speech in game chat is off unless you tick
  **Allow Jev to speak**.
- **Your shard's rules.** Many shards forbid unattended play. jevanced is
  meant to be watched; follow your shard's rules.

## How it fits together

```
run_jevanced.py          Razor Enhanced entry point; hands RE's API objects to the adapter
jevanced/
  razor/adapter.py       the ONLY module that calls Razor Enhanced (read_state, execute)
  state.py               plain-data game state sent to Jev
  jev/client.py          Jev client interface and errors
  jev/choices.py         the options Jev picks from, and the state it sees
  jev/typesafe.py        the Jev client for Typesafe's API
  jev/http.py            HTTPS via .NET inside Razor Enhanced, urllib elsewhere
  jev/stub.py            offline stand-in that only bandages
  bodykinds.py           monster / animal / human from the client's mobtypes.txt
  actions.py             allowed actions and validation of Jev's reply
  controller.py          the loop: read, decide, validate, check kill switch, act
  killswitch.py          the stop flag every step checks
  app.py                 wiring, key and start/stop handling, view model for the UI
  keystore.py            API key storage (DPAPI), masking
  config.py, eventlog.py settings and a redacting activity log
  ui/winforms.py         the window (draws app.view(), forwards button presses)
```

The game loop runs on Razor Enhanced's script thread; the window runs on
its own thread and only calls `JevancedApp` methods.

## Releasing

Bump `__version__` in `jevanced/__init__.py` in a PR. When it merges to
`main`, the Release workflow tests, builds and publishes `v<version>` with
`jevanced.zip` attached, and the installer picks it up.

## Development

```
python -m unittest discover -s tests -t .
ruff check .
```

To run the tests under IronPython too, install the .NET 8 SDK and
`dotnet tool install --global IronPython.Console --version 3.4.2`, then:

```
ipy tools/compile_check.py
ipy -m unittest discover -s tests -t .
```

Shipped code has to stay IronPython 3.4 compatible: no `dataclasses`, no
CPython C extensions.
