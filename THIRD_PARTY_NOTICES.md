# Third-party notices

Cairn's Python and JavaScript dependency versions and integrity hashes are recorded in `uv.lock`
and `ui/package-lock.json`. The release SBOM enumerates the resolved Python runtime environment.
The browser bundle includes the following direct JavaScript works:

| Work | Version family | License |
|---|---:|---|
| React and React DOM | 18.3 | MIT |
| React Router DOM | 6.x | MIT |
| TanStack Query and Virtual | 5.x / 3.x | MIT |
| Visx chart modules | 3.12 | MIT |
| Zustand | 5.x | MIT |
| Dagre | 0.8 | MIT |
| Lucide React | 0.468 | ISC |
| Manrope font | 5.2 package / upstream font | SIL OFL 1.1 |
| JetBrains Mono font | 5.2 package / upstream font | SIL OFL 1.1 |

The bundled Manrope and JetBrains Mono files retain their upstream names and notices. Their common
SIL Open Font License text is included at `licenses/OFL-1.1.txt`. Copyright notices:

- Manrope: Copyright 2019 The Manrope Project Authors.
- JetBrains Mono: Copyright 2020 The JetBrains Mono Project Authors.

Transitive browser dependencies remain subject to their own licenses as identified by the npm
lockfile and package metadata. This notice does not replace those licenses.
