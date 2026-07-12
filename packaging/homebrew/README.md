# Homebrew distribution

Homebrew formulae require the checksum of a published source archive. This repository intentionally does not ship an invalid formula with a placeholder checksum.

After the first PyPI release is published, publish the generated formula in the Cairn Homebrew tap using the source-distribution URL and its SHA-256. Keep the formula in the tap so `brew update` can receive package updates independently of the application repository.
