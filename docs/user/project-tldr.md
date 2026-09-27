# OpenCascade.js: start here

This repo turns the OpenCascade (OCCT) C++ kernel into WebAssembly that JavaScript can call. This fork serves Rockett-CAD with a trimmed kernel and native helpers. The full kernel, tests and docs playground remain. Rockett-CAD is a separate consumer; there is no application server or database here.

**Hard rule:** preserve CAD, CAM, render and PCB/electrical needs. Cut wasted work, not features.

## What runs where

| Part | Job | Needed by |
|---|---|---|
| OCCT | Native CAD engine: shapes, booleans, curves, meshes, file formats. | Kernel. |
| Clang + Python | Read C++ headers; emit wrappers and TypeScript types. | Kernel builders. |
| Emscripten + Embind | Compile C++ to WASM; bridge JavaScript calls to C++. | Kernel builders; the bridge runs with the kernel. |
| JS + WASM + `.d.ts` | Loader glue, the geometry engine, editor types. | App developers. Types do not run geometry. |
| Docusaurus + React | Docs and example playground. | Website only. |

Pins live in [Dockerfile](../../Dockerfile), [package.json](../../package.json), [test/package.json](../../test/package.json) and [website/package.json](../../website/package.json).

## Two build stages

1. [Dockerfile](../../Dockerfile) fetches pinned sources, applies patches, generates wrappers and compiles OCCT and bindings. This is the slow, reusable image.
2. [buildFromYaml.py](../../src/buildFromYaml.py) picks wrapper objects, compiles custom helpers, links the kernel and writes types. Every compiled OCCT source object except `XBRepMesh.o` reaches the linker; the optimiser drops unused code.

A smaller export list does not shrink the first compile. The Dockerfile copies `src/` before compiling, so any edit there, even to the link script, reruns the full compile. Threading is an image build arg, `single-threaded` by default. YAML cannot switch it.

## Pick the right kernel

| Variant | Meaning | Main source |
|---|---|---|
| Rockett, package default | Selected classes plus bulk mesh, STEP bytes, label names, cancellation and cast helpers. Fewer JS/native crossings for common work. | [rockett-cad.yml](../../builds/rockett-cad.yml) |
| Full | Every binding the filters allow. Not every OCCT API. Used by the general tests. | [opencascade.full.yml](../../builds/opencascade.full.yml) |
| Website example | Separate example build. The worker uses the upstream npm loader and types but loads local example JS/WASM. | [customBuild.yml](../../website/ocjs-editor-theme/src/customBuild/customBuild.yml), [worker](../../website/ocjs-editor-theme/src/theme/CodeBlock/opencascade.worker.ts) |

**YAML traps:** empty or omitted `bindings` means all, not none. `additionalCppCode` adds classes for automatic binding generation. `additionalBindCode` is handwritten Embind code. An explicit `emccFlags` replaces the defaults; it does not append. The [schema](../../src/customBuildSchema.py) owns the defaults.

**Loader traps:** the [browser/bundler entry](../../dist/index.js) imports the WASM as an asset; the [Node entry](../../dist/node.js) resolves a file path. Both default to Rockett. Pass matching JS/WASM pairs. `mainJS` and `mainWasm` can swap the kernel, but the [public types](../../dist/index.d.ts) still promise `RockettInstance`. Full and custom builds must check their types against real exports. Website docs keep upstream compiler advice and size figures; current source wins.

[Package filters](../../src/filter/filterPackages.py) exclude Draw test harnesses and native viewer, VTK and platform packages. Mesh helpers are not a native renderer.

## Where to look first

| Need | Owner |
|---|---|
| Upgrade engine or compiler | [Dockerfile](../../Dockerfile), then [patches](../../src/patches/). |
| Missing class or overload | YAML selection, then [filters](../../src/filter/), then [bindings.py](../../src/bindings.py). |
| Wrong generated wrapper or type | [generateBindings.py](../../src/generateBindings.py) drives `bindings.py`. Fix the generator, not the output. |
| Compile flags or source coverage | [Common.py](../../src/Common.py), [compileSources.py](../../src/compileSources.py), [compileBindings.py](../../src/compileBindings.py). |
| Custom helper contract | Rockett YAML C++, [helper types](../../dist/rockett-helpers.d.ts), then the smoke test. |
| Select consumer symbols | [usedSymbols.py](../../src/usedSymbols.py) suggests names from consumer `.ts` text. Keep helper dependencies by hand. |
| Build a Rockett release candidate | [build-rockett-candidate.sh](../../scripts/build-rockett-candidate.sh). Stamps the source commit that smoke requires. |
| Prune or upload artifacts | [scripts](../../scripts/). Dry run by default. Upload takes the candidate directory and still queries GitHub in a dry run. |

`dist/` mixes tracked handwritten loaders and helper types with ignored generated kernels. Never blanket-delete it.

## Which checks answer which question

| Command | Answers | Needs |
|---|---|---|
| `npm test` | Do types, Rockett smoke and the fast tier pass? | What smoke and fast need. |
| `npm --prefix test run smoke:rockett` | Does the smoke type-check against the delivered declarations, then pass helper and geometry smoke on the local Rockett kernel? | Test deps; Rockett JS/WASM/`.d.ts`; a Node that runs `.mts` directly. No Node engine pin. |
| `npm --prefix test run test:fast` | Does general full-kernel behaviour hold? | Test deps, full JS/WASM, and Rockett JS because the loader imports it. |
| `npm --prefix test run test:slow` | Do custom builds, threads, progress and bindings work? | Test deps, a container runtime, local images and artifacts. |
| `npm --prefix test test` | Does the whole Jest suite pass? | What fast and slow need. Excludes Rockett smoke. |

Root `npm test` forwards to `test/`. A fresh clone is not a ready test environment.

Consumer workflows, such as CAM toolpaths and PCB nets, are proved in the consumer, not here.

Proposals, risks and canaries live in [../internals/rockett-performance-canaries.md](../internals/rockett-performance-canaries.md).
