# Contributing to Owly Drop

Thanks for helping! Bug reports, translations and pull requests are all welcome.

## Reporting a bug

Open an [issue](https://github.com/Simon-du06/owly-drop/issues) with:

- your distribution, and the output of `owly --version` and `owly doctor`
- what you did, what you expected and what happened
- the **Technical Log** from the bottom of the window, which shows everything owly printed

If the same problem happens with `owly radio up` and `owly receive` in a terminal, it belongs to [Owly](https://github.com/t4t5/owly/issues) rather than here.

## Setting up

Install the dependencies listed in the [README](README.md#requirements), plus `pytest` and [`ruff`](https://docs.astral.sh/ruff/). Then:

```sh
meson setup build
meson compile -C build run   # try your changes without installing
meson test -C build          # what CI runs
```

There's no need for a working Wi-Fi card: the tests drive the backend with [`tests/fake-owly`](tests/fake-owly). Set `FAKE_OWLY_*` (documented at the top of that script) to make it fail in the ways real owly can. To try the interface without a radio, point the app at the fake one:

```sh
OWLY_BIN="$PWD/tests/fake-owly" meson compile -C build run
```

## How the code is organised

- `src/owly_drop/backend/` knows how to run owly and nothing about GTK. `parser.py` turns owly's output into events and is plain Python. When owly changes what it prints, this is the file to update, along with `tests/test_parser.py` and `tests/fake-owly`.
- The rest of `src/owly_drop/` is the interface. Each widget is a GtkBuilder template in `src/ui/` with a Python class of the same name, connected to the backend through GObject signals and properties.
- New interface files go in `src/owly-drop.gresource.xml`. Any file with translatable strings goes in `po/POTFILES.in`.

## Code style

- `ruff format` and `ruff check` must pass. The settings are in `pyproject.toml`.
- Follow the [GNOME Human Interface Guidelines](https://developer.gnome.org/hig/) for the interface, including Title Case for buttons and headings.
- Anything that comes from the sender's device (names, file names, links) is shown as plain text, never as markup, and is never opened without the user asking.
- Add a test for each backend change.

## Translations

Translations use standard gettext, in `po/`.

- **New language**: add its code to `po/LINGUAS`, then create the file with `meson compile -C build owly-drop-update-po`. That command also refreshes every `.po` file after strings change in the code.
- **Translating**: edit `po/<code>.po` with a tool like [Gtranslator](https://flathub.org/apps/org.gnome.Gtranslator) or Poedit, and check it with `meson test -C build`.

## Sending changes

1. Fork, then create a branch from `main`.
2. Keep each pull request to one change, and explain the why in its description.
3. Make sure `meson test -C build` and `ruff check` pass. CI runs both on every pull request.
4. Add a line to `CHANGELOG.md` under *Unreleased* for anything users will notice.

By contributing, you agree that your work is released under the [MIT license](LICENSE).
