# Owly Drop

A small GNOME app for **AirDrop between iPhones and Linux**. Flip a switch to be visible, accept what an iPhone sends, or drop files on the window to send them back — no terminal needed.

Owly Drop is a graphical front end for [**Owly**](https://github.com/t4t5/owly), which does the actual work: it runs Apple's AWDL Wi-Fi link and the AirDrop protocol on ordinary Wi-Fi cards. Owly Drop drives Owly's `owly` command and shows what happens.

*[Français plus bas.](#français)*

## Features

- **Visible to iPhones** switch: brings Owly's radio up, then starts receiving. Turning it off (or closing the window) gives Wi-Fi back.
- **Incoming requests**: a dialog — and a notification with Accept / Decline buttons when the window isn't in front — showing who sends what. Or accept everything automatically.
- **Received files** listed with buttons to open them or show them in their folder. Links are shown, never opened by themselves.
- **Sending**: pick files or drop them onto the window, choose a nearby iPhone, follow the progress bar.
- The **name** iPhones see and the **download folder** are configurable.
- A collapsible **technical log** with Owly's raw output, for when something goes wrong.
- English and French.

## Requirements

1. **Owly, installed and working with your Wi-Fi card.** Follow [Owly's install guide](https://github.com/t4t5/owly#install), then check your card:
   ```sh
   owly doctor
   ```
   If it says your card isn't on by default, Owly's README explains how to opt in (`/etc/owly/radio.toml`). Make sure one transfer works with `owly radio up` and `owly receive` in two terminals before trying Owly Drop.
2. **Python 3 with GTK 4 and libadwaita 1.6+** (Ubuntu 24.10+, Debian 13+, Fedora 41+, Arch…):
   ```sh
   sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1   # Debian / Ubuntu
   ```

## Install

```sh
git clone https://github.com/Simon-du06/owly-drop.git
cd owly-drop
./install.sh
```

This installs into `~/.local` (no sudo): open **Owly Drop** from your app grid, or run `owly-drop`. Remove it with `./install.sh --uninstall`. You can also run it straight from the clone: `./owly_drop.py`.

## Using it

**Receive**
1. Turn on **Visible to iPhones**. Depending on your card, Owly may turn Wi-Fi off while the radio is up; a banner tells you when it does.
2. On the iPhone, set AirDrop to **Everyone for 10 Minutes**, tap **Share** on a photo, then pick your computer in the AirDrop row.
3. Accept on the computer. The file lands in your download folder.

**Send**: click **Send Files…** or drop files on the window, wait for the iPhone to show up in the list, and click it. The iPhone should be unlocked with AirDrop set to Everyone.

Owly's [known issues](https://github.com/t4t5/owly#known-issues) apply: if the computer stops showing up on the iPhone, close and reopen the share sheet, or restart the iPhone.

## How it works

Owly Drop is a single Python file using GTK 4 and libadwaita. It runs, and reads the output of:

| Command | Used for |
| --- | --- |
| `owly radio up` | holding the radio while you're visible (stopped with SIGTERM, which gives Wi-Fi back) |
| `owly receive --dir … --name …` | receiving; its `accept? [y/N]` prompt becomes the Accept / Decline dialog |
| `owly browse` | listing nearby iPhones |
| `owly send --to …` | sending, with its progress |

It has been written against Owly 0.4.2. Settings live in `~/.config/owly-drop/settings.json`. `OWLY_BIN=/path/to/owly` makes it use another `owly`.

## Development

```sh
tests/selftest.sh
```

checks the translations and the output parser, then runs the whole app against [`tests/fake-owly`](tests/fake-owly), a script that prints what Owly prints: radio up, an iPhone sending a file, accepting it, browsing, sending, radio down. It needs no Wi-Fi card or iPhone, only a graphical session (or `xvfb-run`).

**Translations** are plain gettext files in [`po/`](po/), read at startup. To add a language, copy `po/fr.po` to `po/<code>.po`, translate the `msgstr` lines, and run `tests/selftest.sh` to catch missing strings.

Bug reports and pull requests are welcome. For problems with a Wi-Fi card, the radio, or transfers themselves, please check [Owly's issues](https://github.com/t4t5/owly/issues) first: Owly Drop only shows what Owly does.

## Credits

- [Owly](https://github.com/t4t5/owly) by t4t5 and contributors, which makes all of this possible.
- [OWL](https://github.com/seemoo-lab/owl) and [OpenDrop](https://github.com/seemoo-lab/opendrop) by the Secure Mobile Networking Lab (TU Darmstadt), whose research opened up AWDL and AirDrop.

Owly Drop is an independent project, not affiliated with Owly's authors or with Apple. AirDrop, iPhone and Apple are trademarks of Apple Inc.

## License

[MIT](LICENSE)

---

## Français

**Owly Drop** est une petite application GNOME pour faire de l'**AirDrop entre iPhone et Linux**, sans terminal : un interrupteur pour être visible, une fenêtre pour accepter ce que l'iPhone envoie, et un glisser-déposer pour lui envoyer des fichiers. Elle s'appuie sur [Owly](https://github.com/t4t5/owly), qui fait le vrai travail (le lien Wi-Fi AWDL d'Apple et le protocole AirDrop).

1. Installe [Owly](https://github.com/t4t5/owly#install) et vérifie ta carte Wi-Fi avec `owly doctor`.
2. Installe Owly Drop :
   ```sh
   git clone https://github.com/Simon-du06/owly-drop.git && cd owly-drop && ./install.sh
   ```
3. Ouvre **Owly Drop**, active **Visible par les iPhone**, puis sur l'iPhone : AirDrop sur « Tout le monde pendant 10 minutes », **Partager**, et choisis ton PC.

L'interface s'affiche en français si ton système est en français.
