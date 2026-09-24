import initOpenCascade from "../dist/node.js";
import type { TopoDS_Shape, TopAbs_ShapeEnum } from "../dist/node.js";

const started = performance.now();
const oc = await initOpenCascade({ module: { print: () => {} } });
const bootMs = performance.now() - started;
const failures: string[] = [];

function reason(error: unknown) {
  if (!(error instanceof WebAssembly.Exception)) return String(error);
  const [type, message] = oc.getExceptionMessage(error);
  oc.decrementExceptionRefcount(error);
  return `${type}: ${message}`;
}

function check(name: string, run: () => void) {
  try {
    run();
    console.log(`ok   ${name}`);
  } catch (error) {
    failures.push(name);
    console.log(`FAIL ${name}: ${reason(error)}`);
  }
}

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

function near(actual: number, expected: number, what: string, eps = 1e-6) {
  assert(Math.abs(actual - expected) <= eps, `${what}: ${actual} != ${expected}`);
}

function occtThrow(run: () => void) {
  try {
    run();
  } catch (error) {
    assert(error instanceof WebAssembly.Exception, `not a wasm exception: ${String(error)}`);
    const message = oc.getExceptionMessage(error);
    oc.decrementExceptionRefcount(error);
    return message;
  }
  throw new Error("no exception thrown");
}

function shapes(shape: TopoDS_Shape, type: TopAbs_ShapeEnum) {
  const found: TopoDS_Shape[] = [];
  const explorer = new oc.TopExp_Explorer_2(shape, type, oc.TopAbs_ShapeEnum.TopAbs_SHAPE);
  for (; explorer.More(); explorer.Next()) found.push(explorer.Current());
  explorer.delete();
  return found;
}

const range = () => new oc.Message_ProgressRange_1();
const pnt = (x: number, y: number, z: number) => new oc.gp_Pnt_3(x, y, z);
const S = oc.TopAbs_ShapeEnum;
const box = new oc.BRepPrimAPI_MakeBox_2(1, 2, 3).Shape();
const cylinder = new oc.BRepPrimAPI_MakeCylinder_1(1, 2).Shape();
const line = new oc.BRepBuilderAPI_MakeEdge_3(pnt(0, 0, 0), pnt(3, 4, 0)).Edge();
const circle = new oc.BRepBuilderAPI_MakeEdge_8(new oc.gp_Circ_2(new oc.gp_Ax2_1(), 2)).Edge();
const nonAscii = "Träger ø12 螺丝";

check("versionId", () => {
  const { occt, commit } = oc.versionId();
  assert(/^\d+\.\d+\.\d+/.test(occt), `occt ${occt}`);
  assert(commit.length > 0, "empty commit");
  console.log(`     occt ${occt}, commit ${commit}`);
});

check("meshFace", () => {
  const unmeshed = oc.TopoDS.Face_1(shapes(new oc.BRepPrimAPI_MakeBox_2(1, 1, 1).Shape(), S.TopAbs_FACE)[0]!);
  assert(oc.meshFace(unmeshed) === null, "unmeshed face should give null");
  new oc.BRepMesh_IncrementalMesh_2(box, 0.1, false, 0.5, false).delete();
  for (const shape of shapes(box, S.TopAbs_FACE)) {
    const mesh = oc.meshFace(oc.TopoDS.Face_1(shape));
    assert(mesh, "meshed face gave null");
    const nodes = mesh.positions.length / 3;
    assert(nodes >= 4 && mesh.indices.length >= 6 && mesh.indices.length % 3 === 0, "bad sizes");
    assert(mesh.normals.length === mesh.positions.length, "normals length");
    assert(mesh.indices.every((i) => i < nodes), "index out of range");
    near(Math.hypot(mesh.normals[0]!, mesh.normals[1]!, mesh.normals[2]!), 1, "normal length");
  }
});

check("meshTriangulation", () => {
  const face = oc.TopoDS.Face_1(shapes(box, S.TopAbs_FACE)[0]!);
  const triangulation = oc.BRep_Tool.Triangulation(face, new oc.TopLoc_Location_1(), 0);
  assert(!triangulation.IsNull(), "no triangulation");
  const mesh = oc.meshTriangulation(triangulation);
  assert(mesh.positions.length === 3 * triangulation.get().NbNodes(), "node count");
  assert(mesh.indices.length === 3 * triangulation.get().NbTriangles(), "triangle count");
});

check("sampleEdge line", () => {
  const points = Array.from(oc.sampleEdge(line));
  assert(points.join() === "0,0,0,3,4,0", `points ${points.join()}`);
});

check("sampleEdge circle", () => {
  const points = oc.sampleEdge(circle);
  assert(points.length === 65 * 3, `length ${points.length}`);
  for (let i = 0; i < points.length; i += 3) near(Math.hypot(points[i]!, points[i + 1]!, points[i + 2]!), 2, "radius");
});

check("C++-internal catch in sampleEdge", () => {
  assert(oc.sampleEdge(new oc.TopoDS_Edge()).length === 0, "null edge should sample to nothing");
});

check("OCCT exception via getExceptionMessage", () => {
  const [type, message] = occtThrow(() => oc.TopoDS.Face_1(line));
  assert(type === "Standard_TypeMismatch", `type ${type}: ${message}`);
});

const step = (() => {
  const writer = new oc.STEPControl_Writer_1();
  writer.Transfer_1(box, oc.STEPControl_StepModelType.STEPControl_AsIs, true, range());
  assert(writer.Write("/smoke.step") === oc.IFSelect_ReturnStatus.IFSelect_RetDone, "STEP write");
  writer.delete();
  const bytes = oc.FS.readFile("/smoke.step");
  oc.FS.unlink("/smoke.step");
  return bytes;
})();

check("readStepBytes", () => {
  const reader = new oc.STEPControl_Reader_1();
  assert(oc.readStepBytes(reader, step) === oc.IFSelect_ReturnStatus.IFSelect_RetDone, "read status");
  assert(reader.TransferRoots(range()) === 1, "transfer roots");
  const props = new oc.GProp_GProps_1();
  oc.BRepGProp.VolumeProperties_1(reader.OneShape(), props, false, false, false);
  near(props.Mass(), 6, "volume");
  reader.delete();
});

check("readStepCafBytes", () => {
  const reader = new oc.STEPCAFControl_Reader_1();
  assert(oc.readStepCafBytes(reader, step) === oc.IFSelect_ReturnStatus.IFSelect_RetDone, "read status");
  const doc = new oc.TDocStd_Document(new oc.TCollection_ExtendedString_1());
  assert(reader.Transfer_1(new oc.Handle_TDocStd_Document_2(doc), range()), "transfer");
  const labels = new oc.TDF_LabelSequence_1();
  oc.XCAFDoc_DocumentTool.ShapeTool(doc.Main()).get().GetFreeShapes(labels);
  assert(labels.Length() === 1, `free shapes ${labels.Length()}`);
  reader.delete();
});

check("labelName and setLabelName, non-ASCII", () => {
  const doc = new oc.TDocStd_Document(new oc.TCollection_ExtendedString_1());
  const label = oc.XCAFDoc_DocumentTool.ShapeTool(doc.Main()).get().NewShape();
  assert(oc.labelName(label.NewChild()) === null, "unnamed label should give null");
  oc.setLabelName(label, nonAscii);
  const name = oc.labelName(label);
  assert(name === nonAscii, `name ${name}`);
});

check("extendedToUtf8", () => {
  const text = oc.extendedToUtf8(new oc.TCollection_ExtendedString_2(nonAscii, true));
  assert(text === nonAscii, `text ${text}`);
});

check("upcastCurve", () => {
  const arc = new oc.GC_MakeArcOfCircle_4(pnt(1, 0, 0), pnt(0, 1, 0), pnt(-1, 0, 0)).Value();
  const curve = oc.upcastCurve(arc);
  assert(!curve.IsNull(), "null curve");
  const points = oc.sampleEdge(new oc.BRepBuilderAPI_MakeEdge_24(curve).Edge());
  assert(points.length === 33 * 3, `length ${points.length}`);
  near(points[0]!, 1, "arc start x");
});

check("CancelIndicator", () => {
  const fuse = (isCancelled: () => boolean) => {
    let calls = 0;
    const indicator = new oc.CancelIndicator(() => (calls++, isCancelled()));
    const other = new oc.BRepPrimAPI_MakeBox_3(pnt(0.5, 0.5, 0.5), 1, 1, 1).Shape();
    const result = new oc.BRepAlgoAPI_Fuse_3(box, other, indicator.Start());
    indicator.delete();
    return { calls, done: result.IsDone() };
  };
  const cancelled = fuse(() => true);
  const finished = fuse(() => false);
  assert(cancelled.calls > 0 && !cancelled.done, `cancelled run: ${JSON.stringify(cancelled)}`);
  assert(finished.calls > 0 && finished.done, `finished run: ${JSON.stringify(finished)}`);
});

check("TopoDS casts", () => {
  const casts = [
    [S.TopAbs_VERTEX, oc.TopoDS.Vertex_1],
    [S.TopAbs_EDGE, oc.TopoDS.Edge_1],
    [S.TopAbs_WIRE, oc.TopoDS.Wire_1],
    [S.TopAbs_FACE, oc.TopoDS.Face_1],
    [S.TopAbs_SHELL, oc.TopoDS.Shell_1],
    [S.TopAbs_SOLID, oc.TopoDS.Solid_1],
  ] as const;
  for (const [type, cast] of casts) {
    const cast_ = cast(shapes(box, type)[0]!);
    assert(cast_.ShapeType() === type, `cast to ${type.value}`);
  }
});

check("shapeHash", () => {
  const faces = shapes(box, S.TopAbs_FACE);
  const again = shapes(box, S.TopAbs_FACE);
  const hashes = faces.map((face) => oc.shapeHash(face, 1000));
  assert(hashes.every((h) => Number.isInteger(h) && h >= 0 && h < 1000), `hashes ${hashes}`);
  assert(again.every((face, i) => oc.shapeHash(face, 1000) === hashes[i]), "hash not stable");
  const [type] = occtThrow(() => oc.shapeHash(box, 0));
  assert(type === "Standard_RangeError", `type ${type}`);
});

check("BRepAdaptor_Curve", () => {
  const adaptor = new oc.BRepAdaptor_Curve_2(circle);
  assert(adaptor.GetType() === oc.GeomAbs_CurveType.GeomAbs_Circle, "not a circle");
  near(adaptor.Circle().Radius(), 2, "radius");
});

check("BRepAdaptor_Surface", () => {
  const side = shapes(cylinder, S.TopAbs_FACE)
    .map((face) => new oc.BRepAdaptor_Surface_2(oc.TopoDS.Face_1(face), true))
    .find((adaptor) => adaptor.GetType() === oc.GeomAbs_SurfaceType.GeomAbs_Cylinder);
  assert(side, "no cylindrical face");
  near(side.Cylinder().Radius(), 1, "radius");
});

check("BRepAlgoAPI_Section with a plane", () => {
  const plane = new oc.gp_Pln_3(pnt(0, 0, 1.5), new oc.gp_Dir_5(0, 0, 1));
  const section = new oc.BRepAlgoAPI_Section_5(box, plane, true);
  assert(section.IsDone(), "section not done");
  assert(shapes(section.Shape(), S.TopAbs_EDGE).length === 4, "expected 4 edges");
});

check("gp_Cone", () => {
  const cone = new oc.gp_Cone_2(new oc.gp_Ax3_1(), Math.PI / 6, 1);
  near(cone.SemiAngle(), Math.PI / 6, "semi-angle");
  near(cone.Apex().Z(), -Math.sqrt(3), "apex z");
});

check("gp_Torus", () => {
  const torus = new oc.gp_Torus_2(new oc.gp_Ax3_1(), 3, 1);
  near(torus.Volume(), 6 * Math.PI ** 2, "volume");
  near(torus.Area(), 12 * Math.PI ** 2, "area");
});

const totalMs = performance.now() - started;
console.log(`boot ${bootMs.toFixed(0)} ms, total ${totalMs.toFixed(0)} ms, ${failures.length} failed`);
if (failures.length > 0) process.exit(1);
