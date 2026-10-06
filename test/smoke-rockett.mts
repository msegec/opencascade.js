import initOpenCascade from "../dist/node.js";
import type { TopoDS_Shape, TopAbs_ShapeEnum } from "../dist/node.js";

declare global {
  namespace WebAssembly {
    class Exception {
      is(tag: unknown): boolean;
    }
  }
}

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
  assert(/^[0-9a-f]{40}$/.test(commit), `commit ${commit}`);
  console.log(`     occt ${occt}, commit ${commit}`);
});

check("retained OCJS exception helper", () => {
  const helper = new oc.OCJS();
  assert(oc.OCJS.getStandard_FailureData(0) === null, "null exception pointer");
  helper.delete();
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

check("exact ellipse construction and recovery", () => {
  const ellipse = new oc.gp_Elips_2(new oc.gp_Ax2_1(), 10, 5);
  const maker = new oc.BRepBuilderAPI_MakeEdge_12(ellipse);
  assert(maker.IsDone(), "ellipse edge failed");
  const recovered = new oc.BRepAdaptor_Curve_2(maker.Edge()).Ellipse();
  near(recovered.MajorRadius(), 10, "ellipse major radius");
  near(recovered.MinorRadius(), 5, "ellipse minor radius");
});

check("exact rational, trimmed and periodic B-splines", () => {
  const poles = new oc.TColgp_Array1OfPnt_2(1, 3);
  const rationalCoordinates: [number, number][] = [
    [1, 0],
    [1, 1],
    [0, 1],
  ];
  rationalCoordinates.forEach(([x, y], i) =>
    poles.SetValue_1(i + 1, pnt(x, y, 0)),
  );
  const weights = new oc.TColStd_Array1OfReal_2(1, 3);
  [1, Math.SQRT1_2, 1].forEach((w, i) => weights.SetValue_1(i + 1, w));
  const knots = new oc.TColStd_Array1OfReal_2(1, 2);
  const mults = new oc.TColStd_Array1OfInteger_2(1, 2);
  [0, 1].forEach((u, i) => {
    knots.SetValue_1(i + 1, u);
    mults.SetValue_1(i + 1, 3);
  });
  const spline = new oc.Geom_BSplineCurve_2(
    poles,
    weights,
    knots,
    mults,
    2,
    false,
    true,
  );
  const handle = new oc.Handle_Geom_Curve_2(spline);
  const maker = new oc.BRepBuilderAPI_MakeEdge_24(handle);
  assert(maker.IsDone(), "rational edge failed");
  const adaptor = new oc.BRepAdaptor_Curve_2(maker.Edge());
  const recovered = adaptor.BSpline().get();
  assert(
    recovered.IsRational() && recovered.Degree() === 2,
    "rational curve changed",
  );
  near(recovered.Weight(2), Math.SQRT1_2, "rational weight");
  near(adaptor.Value(0.5).X(), Math.SQRT1_2, "rational midpoint x");
  near(adaptor.Value(0.5).Y(), Math.SQRT1_2, "rational midpoint y");
  const trim = new oc.Geom_TrimmedCurve(handle, 0.2, 0.8, true, false);
  const trimHandle = oc.upcastCurve(new oc.Handle_Geom_TrimmedCurve_2(trim));
  const trimMaker = new oc.BRepBuilderAPI_MakeEdge_24(trimHandle);
  assert(trimMaker.IsDone(), "trimmed edge failed");
  const trimAdaptor = new oc.BRepAdaptor_Curve_2(trimMaker.Edge());
  near(trimAdaptor.FirstParameter(), 0.2, "trim start");
  near(trimAdaptor.LastParameter(), 0.8, "trim end");
  near(
    trimAdaptor.BSpline().get().Weight(2),
    Math.SQRT1_2,
    "trimmed rational weight",
  );
  const periodicPoles = new oc.TColgp_Array1OfPnt_2(1, 4);
  const periodicCoordinates: [number, number][] = [
    [1, 0],
    [0, 1],
    [-1, 0],
    [0, -1],
  ];
  periodicCoordinates.forEach(([x, y], i) =>
    periodicPoles.SetValue_1(i + 1, pnt(x, y, 0)),
  );
  const periodicKnots = new oc.TColStd_Array1OfReal_2(1, 5);
  const periodicMults = new oc.TColStd_Array1OfInteger_2(1, 5);
  [0, 1, 2, 3, 4].forEach((u, i) => {
    periodicKnots.SetValue_1(i + 1, u);
    periodicMults.SetValue_1(i + 1, 1);
  });
  const periodic = new oc.Geom_BSplineCurve_1(
    periodicPoles,
    periodicKnots,
    periodicMults,
    2,
    true,
  );
  const periodicMaker = new oc.BRepBuilderAPI_MakeEdge_24(
    new oc.Handle_Geom_Curve_2(periodic),
  );
  assert(periodicMaker.IsDone(), "periodic edge failed");
  const periodicAdaptor = new oc.BRepAdaptor_Curve_2(periodicMaker.Edge());
  const periodicRecovered = periodicAdaptor.BSpline().get();
  assert(
    periodicRecovered.IsPeriodic() && periodicRecovered.IsClosed(),
    "periodic closure lost",
  );
  near(periodicRecovered.Period(), 4, "period");
  near(
    periodicRecovered.Value(0.25).Distance(periodicRecovered.Value(4.25)),
    0,
    "periodic evaluation",
  );
});

function ulps(a: number, b: number) {
  const view = new DataView(new ArrayBuffer(8));
  const ordered = (x: number) => {
    view.setFloat64(0, x);
    const bits = view.getBigInt64(0);
    return bits < 0n ? -(bits & 0x7fffffffffffffffn) : bits;
  };
  const d = ordered(a) - ordered(b);
  return d < 0n ? -d : d;
}

check("BinTools round trips of a sweep: ranges exact, directions within 1 ulp, then bit-identical", () => {
  const axis = new oc.gp_Ax1_2(pnt(-1, 0, 0), new oc.gp_Dir_5(0, 0, 1));
  const profile = shapes(box, S.TopAbs_FACE)[0]!;
  const cold = new oc.BRepPrimAPI_MakeRevol_1(profile, axis, Math.PI / 2, false).Shape();
  assert(cold.ShapeType() === S.TopAbs_SOLID, "sweep is not a solid");
  const write = (shape: TopoDS_Shape) => {
    assert(oc.BinTools.Write_3(shape, "/smoke.bin", range()), "BinTools write");
    const bytes = oc.FS.readFile("/smoke.bin");
    oc.FS.unlink("/smoke.bin");
    return bytes;
  };
  const read = (bytes: Uint8Array) => {
    oc.FS.writeFile("/smoke.bin", bytes);
    const shape = new oc.TopoDS_Shape();
    assert(oc.BinTools.Read_2(shape, "/smoke.bin", range()), "BinTools read");
    oc.FS.unlink("/smoke.bin");
    return shape;
  };
  const first = read(write(cold));
  const edges = (shape: TopoDS_Shape) =>
    shapes(shape, S.TopAbs_EDGE).flatMap((shape) => {
      const edge = oc.TopoDS.Edge_1(shape);
      const curve = new oc.BRepAdaptor_Curve_2(edge);
      return [curve.FirstParameter(), curve.LastParameter(), oc.BRep_Tool.Tolerance_2(edge)];
    });
  const coldEdges = edges(cold);
  const firstEdges = edges(first);
  assert(coldEdges.includes(Math.PI / 2), "no quarter-turn edge range");
  assert(
    firstEdges.length === coldEdges.length && firstEdges.every((x, i) => Object.is(x, coldEdges[i])),
    "edge ranges or tolerances differ",
  );
  const xyz = (d: { X(): number; Y(): number; Z(): number }) => [d.X(), d.Y(), d.Z()];
  const axes = (a: { Direction(): any; XDirection(): any; YDirection(): any }) =>
    [a.Direction(), a.XDirection(), a.YDirection()].flatMap(xyz);
  const directions = (shape: TopoDS_Shape) => [
    ...shapes(shape, S.TopAbs_FACE).flatMap((face) => {
      const surface = new oc.BRepAdaptor_Surface_2(oc.TopoDS.Face_1(face), true);
      const type = surface.GetType();
      if (type === oc.GeomAbs_SurfaceType.GeomAbs_Plane) return axes(surface.Plane().Position());
      if (type === oc.GeomAbs_SurfaceType.GeomAbs_Cylinder) return axes(surface.Cylinder().Position());
      throw new Error(`unexpected surface ${type.value}`);
    }),
    ...shapes(shape, S.TopAbs_EDGE).flatMap((edge) => {
      const curve = new oc.BRepAdaptor_Curve_2(oc.TopoDS.Edge_1(edge));
      const type = curve.GetType();
      if (type === oc.GeomAbs_CurveType.GeomAbs_Line) return xyz(curve.EvalDN(curve.FirstParameter(), 1));
      if (type === oc.GeomAbs_CurveType.GeomAbs_Circle) return axes(curve.Circle().Position());
      throw new Error(`unexpected curve ${type.value}`);
    }),
    ...shapes(shape, S.TopAbs_EDGE).flatMap((edge) => {
      const found: number[] = [];
      for (let i = 1; ; i++) {
        const pcurve = new oc.Handle_Geom2d_Curve_1();
        const surface = new oc.Handle_Geom_Surface_1();
        oc.BRep_Tool.CurveOnSurface_4(oc.TopoDS.Edge_1(edge), pcurve, surface, new oc.TopLoc_Location_1(), 0, 0, i);
        if (pcurve.IsNull()) return found;
        const tangent = pcurve.get().EvalDN(0, 1);
        const bend = pcurve.get().EvalDN(0, 2);
        found.push(tangent.X(), tangent.Y(), bend.X(), bend.Y());
      }
    }),
  ];
  const coldDirections = directions(cold);
  const firstDirections = directions(first);
  assert(firstDirections.length === coldDirections.length, "direction count differs");
  const worst = coldDirections.reduce((most, x, i) => {
    const d = ulps(x, firstDirections[i]!);
    return d > most ? d : most;
  }, 0n);
  assert(worst <= 1n, `direction drift ${worst} ulps`);
  const firstBytes = write(first);
  const secondBytes = write(read(firstBytes));
  assert(
    secondBytes.length === firstBytes.length && secondBytes.every((b, i) => b === firstBytes[i]),
    "second round trip bytes differ",
  );
});

check("BRepFilletAPI_MakeFillet.Add_5 with radii at points", () => {
  const radii = new oc.TColgp_Array1OfPnt2d_2(1, 2);
  radii.SetValue_1(1, new oc.gp_Pnt2d_3(0, 0.2));
  radii.SetValue_1(2, new oc.gp_Pnt2d_3(1, 0.4));
  near(radii.Value(2).Y(), 0.4, "stored radius");
  const edge = shapes(box, S.TopAbs_EDGE)
    .map((shape) => oc.TopoDS.Edge_1(shape))
    .find((edge) => {
      const curve = new oc.BRepAdaptor_Curve_2(edge);
      return curve.LastParameter() - curve.FirstParameter() === 1;
    });
  assert(edge, "no unit edge");
  const fillet = new oc.BRepFilletAPI_MakeFillet(box, oc.ChFi3d_FilletShape.ChFi3d_Rational);
  fillet.Add_5(radii, edge);
  fillet.Build(range());
  assert(fillet.IsDone(), "fillet not done");
  const props = new oc.GProp_GProps_1();
  oc.BRepGProp.VolumeProperties_1(fillet.Shape(), props, false, false, false);
  assert(props.Mass() < 6, `volume ${props.Mass()}`);
});

const totalMs = performance.now() - started;
console.log(`boot ${bootMs.toFixed(0)} ms, total ${totalMs.toFixed(0)} ms, ${failures.length} failed`);
if (failures.length > 0) process.exit(1);
