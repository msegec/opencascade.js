import type {
  Handle_Geom_Curve,
  Handle_Geom_TrimmedCurve,
  Handle_Poly_Triangulation,
  IFSelect_ReturnStatus,
  Message_ProgressRange,
  OpenCascadeInstance,
  STEPCAFControl_Reader,
  STEPControl_Reader,
  TCollection_ExtendedString,
  TDF_Label,
  TopoDS_Edge,
  TopoDS_Face,
  TopoDS_Shape,
  TopoDS_Shell,
  TopoDS_Solid,
  TopoDS_Vertex,
  TopoDS_Wire,
} from "./opencascade.rockett.js";

export declare class CancelIndicator {
  constructor(isCancelled: () => boolean);
  Start(): Message_ProgressRange;
  delete(): void;
}

type StepBytes = string | ArrayBuffer | Uint8Array;

export type RockettHelpers = {
  meshFace(face: TopoDS_Face): { positions: Float64Array; indices: Uint32Array; normals: Float64Array } | null;
  meshTriangulation(triangulation: Handle_Poly_Triangulation): { positions: Float64Array; indices: Uint32Array };
  sampleEdge(edge: TopoDS_Edge): Float64Array;
  versionId(): { occt: string; commit: string };
  extendedToUtf8(text: TCollection_ExtendedString): string;
  labelName(label: TDF_Label): string | null;
  setLabelName(label: TDF_Label, name: string): void;
  readStepBytes(reader: STEPControl_Reader, bytes: StepBytes): IFSelect_ReturnStatus;
  readStepCafBytes(reader: STEPCAFControl_Reader, bytes: StepBytes): IFSelect_ReturnStatus;
  upcastCurve(curve: Handle_Geom_TrimmedCurve): Handle_Geom_Curve;
  shapeHash(shape: TopoDS_Shape, upper: number): number;
  getExceptionMessage(exception: WebAssembly.Exception): [type: string, message: string];
  decrementExceptionRefcount(exception: WebAssembly.Exception): void;
  CancelIndicator: typeof CancelIndicator;
  TopoDS: {
    Vertex_1(shape: TopoDS_Shape): TopoDS_Vertex;
    Edge_1(shape: TopoDS_Shape): TopoDS_Edge;
    Wire_1(shape: TopoDS_Shape): TopoDS_Wire;
    Face_1(shape: TopoDS_Shape): TopoDS_Face;
    Shell_1(shape: TopoDS_Shape): TopoDS_Shell;
    Solid_1(shape: TopoDS_Shape): TopoDS_Solid;
  };
};

export type RockettInstance = OpenCascadeInstance & RockettHelpers;
