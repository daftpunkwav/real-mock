# public/

Static assets served at the site root (Next.js `public/` convention).

| Path | Contents |
| --- | --- |
| [`avatars/`](avatars/) | Interviewer avatar models (`.glb`) — provenance below |
| `scenes/` | Interview room scene backdrops (SVG) |
| `vendor/skulpt/` | Skulpt distribution used by the in-browser Python code runner |
| `avatar-test.html` | Standalone avatar test page |

## Avatar model provenance

Origins below are what each file's embedded glTF `asset` metadata records
(read from the `.glb` JSON chunk); the repository ships no separate license
files for them.

| File | Origin (embedded metadata) |
| --- | --- |
| `gentle_female.glb`, `young_female.glb` | [Ready Player Me](https://readyplayer.me) (`generator` / `copyright: "Ready Player Me"`) |
| `hr_female.glb` | [Avaturn](https://avaturn.me), exported through Blender (`generator: "Avaturn.me \| Blender"`) |
| `professional_male.glb` | Blender export (Khronos glTF Blender I/O v5.0.21); the upstream model source is not recorded in the file or this repository |
| `senior_male.glb` | Blender export (Khronos glTF Blender I/O v5.0.21); the upstream model source is not recorded in the file or this repository |

The provider terms that governed the original downloads (Ready Player Me,
Avaturn) are not bundled here — check those terms before redistributing the
models outside this project.
