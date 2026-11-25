<p align="center">
  <img src="icons/hicolor/scalable/apps/io.github.henryprzygocki.Ebb.svg" width="112" alt="">
</p>

<h1 align="center">Ebb</h1>

<p align="center">A TIDAL player for Linux, built for lossless and hi-res audio.</p>

Ebb is a GTK 4 / libadwaita desktop app with a Rust audio core. It is a modified version of
[hiresTI](https://github.com/yelanxin/hiresTI) by yelanxin: the playback engine, bit-perfect and
exclusive output, USB Rawlink and the DSP chain are hiresTI's work. Ebb changes how the app feels
to use day to day.

> Ebb is an independent project, not affiliated with or endorsed by TIDAL. You need a TIDAL
> subscription.

## What Ebb changes

**Playing music**

- Space is play/pause wherever focus is (it used to replay the focused track); Ctrl+← / → skip.
- Shuffle plays every track once before repeating, Play Next and Add to Queue work in shuffle,
  and the gapless prefetch loads the track that actually plays next.
- Previous steps back through what really played, even after you edit the queue.
- If your TIDAL login caps streams at AAC 320 (Web and QR logins do, for most tracks), Ebb says
  so and makes switching to the lossless login one click.

**Finding your way**

- Right-click menus on tracks, albums, artists, playlists and mixes (or Menu / Shift+F10).
- Back returns to the page you came from, scrolled to where you were; the mouse's back button
  and Alt+← work too.
- Tab moves between controls; a track list or the sidebar is a single Tab stop, with the arrow
  keys moving inside it.
- Search results show one row per section, with tracks right after artists.
- Removing a track from a playlist can be undone.

**Fitting your screen**

- The window shrinks to 420 px wide and pages adapt; album pages get a compact layout below
  520 px.
- Empty lists say why they are empty, and the idle player bar no longer pretends something is
  loaded.
- A keyboard shortcuts window (Ctrl+?).

**Under the hood**

- The output device is remembered by its stable ID rather than its display name, and the
  PipeWire sink re-attaches after the device resets.
- A rotating log file in `~/.local/state/ebb`, since desktop launches otherwise leave no trace.
- A 1 KB vector app icon (hiresTI's embedded a large raster that could stall desktop shells).

The complete list is the git history after `v1.9.12`.

## Keyboard

| Key | Action |
| --- | --- |
| Space | Play / pause |
| Ctrl+← / Ctrl+→ | Previous / next track |
| Alt+← or mouse back | Back |
| Ctrl+F | Search |
| Q / W / E | Queue / Now Playing / lyrics, visualizer and DSP |
| Esc | Close the open panel |
| Tab, arrows, Enter | Move between controls, move inside a list, activate |
| Menu or Shift+F10 | Menu for the focused item |
| Ctrl+? | All shortcuts |
| Ctrl+Q | Quit (closing the window keeps playing in the tray) |

## Install

**Arch Linux**: [`ebb-git`](https://aur.archlinux.org/packages/ebb-git) on the AUR builds the newest
commit on `main`. With an AUR helper, `paru -S ebb-git` or `yay -S ebb-git`; by hand:

```sh
git clone https://aur.archlinux.org/ebb-git.git
cd ebb-git && makepkg -si
```

Later commits come in with `paru -Syu --devel` or `yay -Syu --devel`, or by running `makepkg -si`
again. The package replaces `hiresti` (answer `y` when pacman offers to remove it). Start Ebb from
your app launcher, or run `ebb-player`: plain `ebb` is a TeX Live tool. On first start Ebb moves
hiresTI's login, settings, history and caches from `~/.config/hiresti`, `~/.cache/hiresti`,
`~/.local/share/hiresti` and `~/.local/state/hiresti` to the matching `ebb` directories, leaving
symlinks at the old names.

**From source**, with the libraries listed under `depends` in
[aur/ebb-git/PKGBUILD](aur/ebb-git/PKGBUILD):

```sh
cargo build --release --manifest-path src_rust/rust_audio_core/Cargo.toml
cargo build --release --manifest-path src_rust/rust_viz_core/Cargo.toml
python3 src/main.py
```

## Credits and license

Ebb is based on [hiresTI](https://github.com/yelanxin/hiresTI) by yelanxin, released under the
GNU General Public License, version 3 or later. Ebb is a modified version, distributed under the
same license (see [LICENSE](LICENSE)); it has been modified by HenryPrzygocki since November 2026,
as recorded in the git history after `v1.9.12`. hiresTI's own documentation is kept in
[docs/upstream](docs/upstream).

If Ebb is useful to you, consider [sponsoring yelanxin](https://github.com/sponsors/yelanxin):
the engine Ebb plays through is their work. Please report Ebb problems
[to Ebb](https://github.com/HenryPrzygocki/Ebb/issues), not to hiresTI.
