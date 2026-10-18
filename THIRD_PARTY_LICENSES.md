# Third-party software and licensing notes

## Stockfish

This project installs the Debian-packaged Stockfish engine inside its Docker image; it does not include a prebuilt Stockfish executable in the source ZIP. Stockfish is licensed under the GNU General Public License, version 3 (GPL-3.0-or-later). A copy of the GPL-3.0 license is included in `licenses/GPL-3.0.txt`.

The Dockerfile uses Debian Trixie's `stockfish` package. Debian's corresponding source package is listed at:

- https://packages.debian.org/source/trixie/stockfish
- https://packages.debian.org/trixie/stockfish
- Upstream project and licensing terms: https://github.com/official-stockfish/Stockfish

Before distributing a built image or integrating Stockfish into a commercial product, review GPL compliance for the exact binary/source version shipped. Retain the corresponding Debian source package and copyright notices, and make the source available as required by the applicable license. This note is informational and is not legal advice.

## Python packages

Python dependencies are installed from `requirements.txt`; consult each dependency's own license when distributing the application.
