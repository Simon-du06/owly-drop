# Owly Drop

[![CI](https://github.com/Simon-du06/owly-drop/actions/workflows/ci.yml/badge.svg)](https://github.com/Simon-du06/owly-drop/actions/workflows/ci.yml)

A small GNOME app for **AirDrop between iPhones and Linux**. Flip a switch to be visible, accept what an iPhone sends, or drop files on the window to send them back. No terminal needed.

Owly Drop is a graphical front end for [**Owly**](https://github.com/t4t5/owly), which does the actual work: it runs Apple's AWDL Wi-Fi link and the AirDrop protocol on ordinary Wi-Fi cards. Owly Drop drives Owly's `owly` command and shows what happens.

*[Français plus bas.](#français)*

## Features

- **Visible to iPhones** switch: brings Owly's radio up, then starts receiving. Turning it off, or closing the window, gives Wi-Fi back.
- **Incoming requests**: a dialog, plus a notification with Accept and Decline buttons when the window isn't in front, showing who sends what. You can also accept everything automatically.
- **Received files**: a list with buttons to open each file or show it in its folder. Links are shown, never opened by themselves.
- **Sending**: pick files (<kbd>Ctrl</kbd>+<kbd>O</kbd>) or drop them onto the window, choose a nearby iPhone, and follow the progress bar. A transfer can be cancelled.
- **Settings**: the **name** iPhones see and the **download folder**.
- A collapsible **technical log** with Owly's raw output, for when something goes wrong.
- English and French.

## Requirements

1. **Owly, installed and working with your Wi-Fi card.** Follow [Owly's install guide](https://github.com/t4t5/owly#install), then check your card:
   ```sh
   owly doctor
   ```
   If it says your card isn't on by default, Owly's README explains how to opt in (`/etc/owly/radio.toml`). Make sure one transfer works with `owly radio up` and `owly receive` in two terminals before you try Owly Drop.
2. **GTK 4 and libadwaita 1.6 or newer for Python** (Ubuntu 25.04+, Debian 13+, Fedora 41+, Arch…), and the tools to build the app:
   ```sh
   # Debian / Ubuntu
   sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 \
     meson gettext libglib2.0-dev-bin desktop-file-utils
   # Fedora
   sudo dnf install python3-gobject gtk4 libadwaita meson gettext glib2-devel desktop-file-utils
   ```

## Install

```sh
git clone https://github.com/Simon-du06/owly-drop.git
cd owly-drop
meson setup build --prefix="$HOME/.local"
meson install -C build
```

Then open **Owly Drop** from your app grid, or run `owly-drop` (with `~/.local/bin` on your `PATH`). To install it for every user, leave out `--prefix` and run `sudo meson install -C build`. To remove it, run `ninja -C build uninstall`.

## Using it

**Receive**
1. Turn on **Visible to iPhones**. Depending on your card, Owly may turn Wi-Fi off while the radio is up; a banner tells you when it does.
2. On the iPhone, set AirDrop to **Everyone for 10 Minutes**, tap **Share** on a photo, then pick your computer in the AirDrop row.
3. Accept on the computer. The file lands in your download folder.

**Send**: click **Send Files…** or drop files on the window, wait for the iPhone to show up in the list, and click it. The iPhone should be unlocked with AirDrop set to Everyone.

Owly's [known issues](https://github.com/t4t5/owly#known-issues) apply. If the computer stops showing up on the iPhone, close and reopen the share sheet, or restart the iPhone.

## How it works

Owly Drop runs `owly` commands and reads what they print:

| Command | Used for |
| --- | --- |
| `owly radio up` | holding the radio while you're visible; SIGTERM gives Wi-Fi back |
| `owly receive --dir … --name …` | receiving; its `accept? [y/N]` prompt becomes the Accept / Decline dialog |
| `owly browse` | listing nearby iPhones |
| `owly send --to …` | sending, with its progress |

The code is split in two:

```
src/owly_drop/
├── backend/           no GTK: runs owly and turns its output into GObject signals
│   ├── parser.py      owly's output → events (pure Python)
│   ├── process.py     a command read line by line on the GLib main loop
│   ├── session.py     being visible: radio up + receive, incoming requests
│   ├── browser.py     owly browse
│   └── transfer.py    owly send
├── application.py     actions, About dialog, Unix signals
├── window.py          the main window (src/ui/window.ui)
├── send_dialog.py, request_dialog.py, received_row.py, transfer_row.py
├── settings.py        GSettings (data/*.gschema.xml)
└── formatting.py
```

It was written against Owly 0.4.2. Settings are stored in GSettings under `io.github.Simon_du06.OwlyDrop`. Setting `OWLY_BIN=/path/to/owly` makes it use another `owly` binary.

## Development

```sh
meson setup build
meson compile -C build run   # runs from the build directory, nothing installed
meson test -C build          # tests, and validates the desktop, metainfo and schema files
```

The tests need no Wi-Fi card or iPhone. They run the backend against [`tests/fake-owly`](tests/fake-owly), a script that prints what Owly prints. `pytest` on its own also works from the source tree. See [CONTRIBUTING.md](CONTRIBUTING.md) for the code style, translations and how to send changes.

For problems with a Wi-Fi card, the radio or the transfers themselves, check [Owly's issues](https://github.com/t4t5/owly/issues) first: Owly Drop only shows what Owly does.

## Credits

- [Owly](https://github.com/t4t5/owly) by t4t5 and contributors, which makes all of this possible.
- [OWL](https://github.com/seemoo-lab/owl) and [OpenDrop](https://github.com/seemoo-lab/opendrop) by the Secure Mobile Networking Lab (TU Darmstadt), whose research opened up AWDL and AirDrop.

Owly Drop is an independent project. It isn't affiliated with Owly's authors or with Apple. AirDrop, iPhone and Apple are trademarks of Apple Inc.

## License

[MIT](LICENSE)

---

## Français

**Owly Drop** est une petite application GNOME pour faire de l'**AirDrop entre iPhone et Linux** sans terminal. Un interrupteur te rend visible, une fenêtre te laisse accepter ce que l'iPhone envoie, et un glisser-déposer lui envoie des fichiers. Elle s'appuie sur [Owly](https://github.com/t4t5/owly), qui fait le vrai travail (le lien Wi-Fi AWDL d'Apple et le protocole AirDrop).

1. Installe [Owly](https://github.com/t4t5/owly#install) et vérifie ta carte Wi-Fi avec `owly doctor`.
2. Installe les dépendances (voir *Requirements* plus haut), puis Owly Drop :
   ```sh
   git clone https://github.com/Simon-du06/owly-drop.git && cd owly-drop
   meson setup build --prefix="$HOME/.local" && meson install -C build
   ```
3. Ouvre **Owly Drop** et active **Visible par les iPhone**. Sur l'iPhone, règle AirDrop sur « Tout le monde pendant 10 minutes », touche **Partager**, puis choisis ton PC.

L'interface s'affiche en français si ton système est en français.
