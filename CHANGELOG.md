# Changelog

All notable changes to Owly Drop are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-11-08

A rewrite into a modular code base, with the same features.

### Added
- About dialog and main menu, and <kbd>Ctrl</kbd>+<kbd>O</kbd> to send files.
- A transfer can be cancelled.
- AppStream metainfo, so software centres can show the app.
- Unit and integration tests run against a fake owly, and continuous integration.
- Contributing guide.

### Changed
- Built and installed with Meson instead of `install.sh`.
- Settings are stored with GSettings instead of `~/.config/owly-drop/settings.json`, which is no longer read.
- Interfaces are GtkBuilder files, and translations use standard gettext.
- The French translation uses "vous", as GNOME's French translations do.
- The code is split into a GTK-free backend (`owly_drop.backend`) and the interface.

## [0.1.0] - 2026-11-08

### Added
- First release: receive and send files with iPhones through Owly, in English and French.

[Unreleased]: https://github.com/Simon-du06/owly-drop/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Simon-du06/owly-drop/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Simon-du06/owly-drop/releases/tag/v0.1.0
