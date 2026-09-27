import initOpenCascade, { OpenCascadeInstance } from "opencascade.js/dist/node";
import * as path from 'path';
import { fileURLToPath } from 'url';
import { jest } from "@jest/globals";
import { customBuild, requireThreading } from "./containerBuild";
jest.setTimeout(10000);

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const it_ = process.env.skipMultiThreaded ? it.skip : it;

beforeAll(() => requireThreading("multi-threaded"));

it_("can create custom build: multi-threaded", () => {
  expect(customBuild("multi-threaded")).toBe(0);
});

let mainJs: any = undefined;
let oc: OpenCascadeInstance = undefined;

it_("can load custom build: multi-threaded", async () => {
  mainJs = await import(path.join(__dirname, "customBuilds", "customBuild.multi-threaded.js"));
  oc = await initOpenCascade({
    mainJS: mainJs.default,
    mainWasm: path.join(__dirname, "customBuilds", "customBuild.multi-threaded.wasm"),
  });
  expect((oc as any).wasmMemory.buffer).toBeInstanceOf(SharedArrayBuffer);
});

it_("can tessellate in multi-threaded mode", async () => {
  const spheres = new Array(50).fill(undefined).map((_, i) => new oc.BRepPrimAPI_MakeSphere_5(new oc.gp_Pnt_3(i, 0, 0), 2));
  const aRes = new oc.TopoDS_Compound();
  const aBuilder = new oc.BRep_Builder();
  aBuilder.MakeCompound(aRes);
  spheres.map(s => aBuilder.Add(aRes, s.Shape()));
  const tessellation = new oc.BRepMesh_IncrementalMesh_2(aRes, 0.1, false, 0.1, true);
  tessellation.Perform_1(new oc.Message_ProgressRange_1());
  expect(tessellation.IsDone()).toBeTruthy();
  oc.PThread.terminateAllThreads();
});
