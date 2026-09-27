# Rockett-CAD performance canaries

Source snapshot: opencascade.js `33fc293`, tag `v2.0.0-msegec.occt801.2`;
Rockett-CAD evidence rechecked at `3eeefed`. Rockett-CAD installs that
release. The local `dist/` Rockett kernel was built at `1697f65`, so its WASM
differs; the local full kernel was relinked at `33fc293`. Probe the artifact
you mean to change.

Items are ranked proposals, not an approved backlog. Item numbers are
stable; do not renumber. Call savings are static estimates until a canary
measures them.

A canary is a small real check for one failure. Make it fail for the fault it
guards, then prove the fix. Passing proves that case, not the whole kernel.

## Start with avoided work and ownership

### 1, 2 and 3: done downstream

Rockett-CAD shipped all three:

- 1, release export meshes and the copied shape.
- 2, calculate edge centroids only when names collide.
- 3, keep viewport payloads out of state-only requests.

### 4. Omit normals from the native export mesh path

Evidence: `meshCopy` in
[mesh.ts](https://github.com/msegec/Rockett-CAD/blob/main/server/src/geometry/mesh.ts) calls `meshFace`,
which computes and copies Float64 normals
([rockett-cad.yml](../../builds/rockett-cad.yml) lines 264-281). `exportMesh`
in [exporters.ts](https://github.com/msegec/Rockett-CAD/blob/main/server/src/geometry/exporters.ts)
keeps only positions and indices, and `writeStl` computes its own facet
normals.

Change: reuse the native array extraction with triangulation, transform and
reversed-face inputs, allowing export to omit normals. Keep viewport output.
Do not substitute `meshTriangulation` directly: it uses an identity transform
and non-reversed winding.
Canary: curved, transformed and reversed faces, plus exact imported meshes;
measure native normal work, transferred bytes and export wall time separately.
Gate: identical positions, indices, winding and decoded export geometry;
viewport normals remain unchanged.

### 5. Update one exact triangle in one native call

Evidence: `setExactTriangle` in
[mesh.ts](https://github.com/msegec/Rockett-CAD/blob/main/server/src/geometry/mesh.ts) makes 17 Embind
calls per triangle. The triangulation wrapper is adopted by a `Handle_Poly_Triangulation`, so
deleting it from JS needs a fork ruling. A native helper never creates that
wrapper.

Change: one native helper accepts the builder, face and nine coordinates,
constructs the triangulation and updates the face. Preserve mesh purpose 32
and handle ownership. Do not change sewing or topology construction.
Canary: bounded 10k-triangle import first; then 100k if the smaller run stays
within the chosen time and memory caps. Count live handles across repeated
imports. The static estimate is 1.6 million fewer boundary calls at 100k
triangles.
Gate: exact node coordinates, triangle order, winding, purpose selection,
round-trip geometry and repeated-import ownership all remain correct. Prove
exact imported meshes still bypass BRepMesh.

## Build canaries

### 6. Separate server and client build caches: moved

Rockett-CAD owns this; it is not kernel work.

### 7. Remove the unused legacy custom exception class: done

Rockett no longer requests `OCJS`, and
[buildFromYaml.py](../../src/buildFromYaml.py) skips custom generation and
compilation when `additionalCppCode` is empty, still clearing old custom
bindings. One relink sample: 385 s before, 306 s after; generation and
compilation were 75 s of it. The export inventory lost only `OCJS`. A build
that keeps a custom class produced byte-identical output. The full build
keeps the class. Rockett-CAD's tracked code no longer references it.

### 8. Feed OCCT source objects to the linker through an archive

Evidence: [buildFromYaml.py](../../src/buildFromYaml.py) lines 96-116
select binding objects but pass every source object except `XBRepMesh.o`
directly to the linker. [Common.py](../../src/Common.py) lines 7-10 enable
LTO and O3.

Every custom build now starts near 3.9 MB of WASM: passing each object
keeps every static initialiser (TDF attributes, `Standard_GUID` statics,
`TObj_Persistence`, `StepData_EnumTool`, `Units_UnitsSystem`, VrmlData),
which pulls in BRepMesh, Geom, TObj and XCAFDoc.

Change: A/B an indexed source-object archive against the current input list.
Keep selected Embind registration objects explicit.
Canary: same Rockett configuration; measure link time, peak RSS, module size
and cold initialisation. Existing LTO may limit the gain.
Gate: export inventory, STEP/IGES round trips, booleans, meshing and exception
fixtures. Static initialisers are a risk; do not blindly archive bindings.

### 9. Stop link-script edits rebuilding the entire compiler image

Evidence: [Dockerfile](../../Dockerfile) line 30 copies all `src` before
the generation/binding/source compilation step at lines 47-52.

Change: copy compilation inputs first and link-only scripts after object
compilation. Separate source compilation from generator inputs only where
their dependency boundaries permit it.
Canary: warm build, change only a link-script comment, rebuild.
Gate: compilation stays cached, while changes to flags, filters or patches
still invalidate the appropriate objects. Prove one clean build as well.
This affects image maintenance builds, not ordinary YAML relinks.

### 10. Test compiler scheduling only if traces show a long tail

Evidence: [compileSources.py](../../src/compileSources.py) lines 105-106
and [compileBindings.py](../../src/compileBindings.py) lines 35-36 use
CPU-count pools and default `Pool.map` chunking.

Canary: same clean object set and fixed worker count; compare default chunks
with `chunksize=1`. Separately vary worker count if memory pressure appears.
Gate: object inventory and smoke checks match. Measure idle-core tail and
peak memory; reject a scheduling change without a useful wall-time gain.

## Build and test hygiene

### 11. Give the fork one local build and test route: partly done

Root `npm test` runs Rockett smoke, then the fast tier. Still open: it needs
`npm install` in `test/` first, and `README.md` links upstream docs,
examples and CI. `scripts/build-rockett-candidate.sh` is the build route.
Canary: a fresh checkout follows the route to a passing smoke run with no
hidden setup.

### 12. One runner for slow container tests: done, tier red

[containerBuild.ts](../../test/containerBuild.ts) owns runtime, image, user,
mounts and failure handling. It defaults to podman and
`localhost/opencascade.js:<package version>`, never pulls, and fails on
runtime errors (exit 125 and above) instead of passing tests that expect a
non-zero build. The docker route is untested.

Results at `33fc293`: `testBindings` 18 of 18, `customBuilds` 6 of 6,
`multi-threaded` fails fast because no threaded image exists.
- Emscripten 3.1.68 (#22591) checks Embind argument counts only under
  `ASSERTIONS`. `-sASSERTIONS=1` also makes int conversion strict, which
  breaks the lenient-conversion checks, so `testBindings` now asserts that
  extra arguments are ignored.
- Size baselines were reset to the OCCT 8 port: `simple` 97,517 / 3,922,987
  / 7,167 bytes; `no-exceptions` 201,546 / 58,891,358 / 9,767,968. The
  `no-exceptions` link needs more than 12 GB; it passed at 24 GB.
- Emscripten 3.1.68 (#22598) stopped emitting `.worker.js`. The threaded
  test no longer renames it, and `multi-threaded.yml` now carries the current
  default flags plus the `wasmMemory` and `PThread` exports. Not run.
- Explicit `emccFlags` replace the defaults, so `multi-threaded.yml` and
  `no-exceptions.yml` copy them and go stale on every toolchain change. An
  append option in the schema would remove the copies.

Still open: replace recursive `chmod 777` ([Dockerfile](../../Dockerfile)
lines 51-52) with explicit ownership. That needs an image rebuild.

### 13. Invalidate reused outputs on their real inputs

Evidence: source objects ([compileSources.py](../../src/compileSources.py)
line 58), binding objects ([compileBindings.py](../../src/compileBindings.py)
line 22) and generated bindings
([generateBindings.py](../../src/generateBindings.py) line 88) are skipped
when the output file exists. Image builds start from an empty tree, but
`.devcontainer/devcontainer.json` bind-mounts a persistent `build/`. There,
a header, flag or threading change can link stale objects.

Change: key reuse on compiler, flags, threading, sources and headers before
relying on any persistent tree. Item 9 is the simpler first step.
Canary: a no-change build reuses work; a changed source, header or flag
rebuilds the affected outputs.

### 14. Fail loudly on cleanup and parser errors: done

Cleanup and directory creation ignore only a missing or existing path, and
`applyPatches.py` catches only a failed `patch`. A full OCCT parse emits zero
Clang diagnostics today, so the generator now fails on any error or fatal
diagnostic ([generateBindings.py](../../src/generateBindings.py), `parseFiles`).
A custom header with a syntax error now stops at parse time with the Clang
message, instead of failing later in the PCH compile.

Still open: skipped classes (generateBindings.py lines 94-95) and TypeScript
`any` fallbacks ([bindings.py](../../src/bindings.py)) print and continue.
Gate for any change there: export inventory unchanged and no new `any`.

### 15. Record build identity at build time: done

[buildFromYaml.py](../../src/buildFromYaml.py) sorts each walk before it
feeds link input and declarations. `scripts/upload-release-assets.sh` now
takes `TAG CANDIDATE_DIR` and publishes the candidate's build-time
`build-info.txt`. It refuses when that file is missing, its `Source commit`
is not the tag commit, or the candidate's `SHA256SUMS` fails. It uploads only
what the candidate lists, so a stray full kernel in `dist/` no longer ships.

Still open: `build-rockett-candidate.sh` does not refuse a dirty tree, its
`*.tgz` glob can pick up a stale tarball from a reused output directory, and
`build-info.txt` does not record the YAML config.

### 16. Import build config without a container: done

[Common.py](../../src/Common.py) discovers OCCT headers and Clang paths only
when called, and caches them. [customBuildSchema.py](../../src/customBuildSchema.py)
gives main and extra builds one rule set, and buildFromYaml.py runs only as a
script. Schema validation works with `/occt` hidden and on the host;
normalized configs, include flags and a Rockett relink are byte-identical.
compileSources.py no longer walks OCCT a second time.

`dist/index.js` and `dist/node.js` repeat one loader body; sharing it adds a
published module, so leave them until a third entry appears.

### 17. Split god files by decision, not by size

| File | Burden | Smallest useful cut |
|---|---|---|
| [bindings.py](../../src/bindings.py) | Types, inheritance, overloads, references, strings, C++ and TS output. `EmbindBindings.processMethodOrProperty` alone carries reference wrappers, string copies, overload suffixes, statics and fields. | Share type and signature decisions; keep output writers distinct. |
| [filterClasses.py](../../src/filter/filterClasses.py), [filterMethodOrProperties.py](../../src/filter/filterMethodOrProperties.py) | Exact exclusions as `if` chains, each with its compile-error comment. | Exact exclusions become sets or maps with reasons; semantic checks stay code. |
| [rockett-cad.yml](../../builds/rockett-cad.yml) | Symbol list plus native C++. | Split native source out only if navigation pain earns a new build input. |
| [generateBindings.py](../../src/generateBindings.py) | Parsing, scheduling, handle typedefs, two output passes. | Keep cached parsing; name stages before splitting. |
| [buildFromYaml.py](../../src/buildFromYaml.py) | CLI, cleanup, checks, compile and link, plus static `FS` type text in `runBuild`. | Move the static type text out when touched. |
| `testBindings.test.ts`, `index.test.ts` | Mostly fixtures. | Share setup; no size-based splits. |

Gate for bindings and filters: same export names, overload suffixes and TS
types; binding fixtures pass.

### 18. Check the helper contract against delivered artifacts: done

`smoke:rockett` now runs `tsc` over
[smoke-rockett.mts](../../test/smoke-rockett.mts) against the delivered
declarations before running it. A deliberately wrong helper return type fails
with 12 errors. The helper declarations were correct.

Limits: shape subclasses are structurally identical, so swapping `TopoDS_Edge`
for `TopoDS_Face` in a helper signature still passes. `skipLibCheck` hides
850 errors in the generated declarations, so a class the trimmed build drops
from a helper import becomes `any` silently. Rockett-CAD types the kernel as
`any`, so it checks none of this.

### 19. Give website preview resources a release owner

Evidence: `OCJSPreview.tsx` caches one worker for the page (lines 13-18) and
never terminates it. Each preview creates a Blob URL (line 23) that is never
revoked. `opencascade.worker.ts` never deletes the native objects user code
creates, and runs that code with `eval` (line 45) by design. The worker does
not make hostile code safe; keep that trust model written down.
Change: revoke URLs and release native handles per run.
Canary: repeated preview and navigation reach stable live handle, URL and
worker counts after warm-up; geometry stays equal.

The website already sits outside kernel work: the Dockerfile copies only
`src`, and tests never read `website/`.

### 20. Fix generator gaps the type check and OCCT 8 exposed: types done

C strings are now typed `string`, and enum members carry their enum's type
with `readonly value: number` ([bindings.py](../../src/bindings.py)). Smoke
compiles with no casts. Full kernel: 3,994 C-string and 3,631 enum-member
types changed; export names are identical.

Still open:
- One enum type is both the container and its values, because
  buildFromYaml.py exports enums as `X: X`. So `oc.TopAbs_ShapeEnum.value`
  type-checks but is undefined at runtime. Fix: emit a separate container
  type and export `X: X_Enum` (or similar), then regenerate declarations.
- Constructors taking a raw `const char*`, such as `Standard_OutOfMemory`,
  are unbound at runtime ("unbound types: PKc").
- OCCT 8 made `TopoDS` a namespace of free functions. The generator binds
  only classes and structs (bindings.py lines 26-33, generateBindings.py line
  250), so Rockett and the full YAML each hand-write the same cast shim, and
  the full build has no typings for it. Binding namespace functions needs an
  image rebuild.
Canary: full and Rockett declare `TopoDS` from generated code; the export
inventory otherwise stays the same.

### 21. Decide what the package publishes: done

Root `package.json` lists the loaders, their types, `rockett-helpers.d.ts` and
the Rockett kernel in `files`. Rockett-CAD imports only `dist/node.js`, and
both loaders import only Rockett, so the full kernel stays a local test
artifact. `npm pack` went from 17 files and 28.3 MB to 11 files and 8.9 MB.

## Comparison protocol and boundaries

Use a one-off harness around existing fixtures, not a permanent new framework.
Alternate baseline/candidate runs three to five times; report median and raw
samples. Report p95 only with enough samples to support it. Separate cold and
warm behaviour, peak RSS, WASM capacity and live allocations/handles. WASM
capacity alone cannot prove a leak. Start with bounded fixtures; set time and
memory caps before heavy 100k-triangle or full compiler experiments. Keep a
change only when its gain exceeds noise and its geometry/ownership gates pass.
smoke-rockett.mts prints boot and total time, but it has no threshold and is
not a leak soak.

Removal gate: no symbol, helper, format or dependency goes because today's
Rockett scan misses it. The planned group (`BRepAlgoAPI_Section`, `gp_Cone`,
`gp_Torus` for CAM-010 and REF-010) is checked by smoke; keep the helper,
test and planned groups. Kernel-side coverage: a representative part builds,
modifies, measures, exports and imports with the same topology, units and
geometry within tolerance, for each required format and direction; item 4
covers mesh shape, winding and normals. Consumer workflows, including CAM
toolpaths, PCB nets and routing, are proved in Rockett-CAD. The package
filters exclude Draw, VTK and native viewer packages; revisit them against
real needs, never blindly.

Do not repeat the slim-kernel work already shipped. Defer threads and
SIMD until measurements attribute remaining time to work they can improve.

Keep: pinned engine and compiler inputs, common flags, precompiled headers,
cached Clang lookups, selected exports, native bulk helpers, test tiers,
dry-run operations and asset hashes.

Avoid: an engine rewrite, a new abstraction framework, blanket TypeScript
conversion, deleting compatibility rules without proof, and caches added
before invalidation is sound.

Relinks and test runs cited above used the local build image at `33fc293`;
one sample each unless stated.
