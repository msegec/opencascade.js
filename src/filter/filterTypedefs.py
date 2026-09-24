def filterTypedef(typedef, additionalInfo=None):
  # Cannot register type 'SelectMgr_Vec3' / 'SelectMgr_Mat4' twice
  if typedef.spelling in [
    "SelectMgr_Vec3",
    "SelectMgr_Mat4",
  ]:
    return False

  # error: ?
  if (
    typedef.spelling == "Handle_PCDM_Reader" or
    typedef.spelling == "Handle_PCDM_ReadWriter_1"
  ):
    return False

  # Cannot register type 'Handle_Graphic3d_Structure' twice, conflicting with Handle_Prs3d_Presentation
  if typedef.spelling == "Handle_Graphic3d_Structure":
    return False

  # error: unknown type name 'Handle_Xw_Window'; did you mean 'Handle_Cocoa_Window'?
  if typedef.spelling == "Handle_Xw_Window":
    return False

  # error: member pointer refers into non-class type 'opencascade::handle<TCollection_HAsciiString> (*)(const opencascade::handle<MoniTool_TypedValue> &, const opencascade::handle<TCollection_HAsciiString> &, bool)'
  # error: 'MoniTool_ValueInterpret' (aka 'handle<TCollection_HAsciiString> (*)(const handle<MoniTool_TypedValue> &, const handle<TCollection_HAsciiString> &, const bool)') is not a class, namespace, or enumeration
  if typedef.spelling == "MoniTool_ValueInterpret":
    return False

  # error: member pointer refers into non-class type 'opencascade::handle<TCollection_HAsciiString> (*)(const opencascade::handle<Interface_TypedValue> &, const opencascade::handle<TCollection_HAsciiString> &, bool)'
  # error: 'Interface_ValueInterpret' (aka 'handle<TCollection_HAsciiString> (*)(const handle<Interface_TypedValue> &, const handle<TCollection_HAsciiString> &, const bool)') is not a class, namespace, or enumeration
  if typedef.spelling == "Interface_ValueInterpret":
    return False

  # error: call to implicitly-deleted copy constructor of 'BRepClass3d_SolidClassifier'
  # error: object of type 'BRepClass3d_SolidClassifier' cannot be assigned because its copy assignment operator is implicitly deleted
  if typedef.spelling == "TopOpeBRepTool_IndexedDataMapOfSolidClassifier":
    return False

  # error: object of type 'BRepClass3d_SolidClassifier' cannot be assigned because its copy assignment operator is implicitly deleted
  # error: rvalue reference to type 'BRepClass3d_SolidClassifier' cannot bind to lvalue of type 'BRepClass3d_SolidClassifier'
  if typedef.spelling == "TopOpeBRepTool_IndexedDataMapOfSolidClassifier":
    return False

  # error: 'NCollection_UBTreeFiller' is not a class, namespace, or enumeration
  if typedef.spelling == "Extrema_UBTreeFillerOfSphere":
    return False

  # error: use of undeclared identifier 'Element_t'
  # no matching function for call to object of type 'std::function<bool (NCollection_Mat4<float> &, int &, emscripten::val)>
  if typedef.spelling in [
    "Graphic3d_Mat4",
    "Graphic3d_Mat4d"
  ]:
    return False

  # error: use of undeclared identifier 'thePosition'
  if typedef.spelling == "XCAFDimTolObjects_DatumModifiersSequence":
    return False

  # causes extreme memory growth which fails the build (see corresponding methods filter)
  if "::Iterator" in typedef.underlying_typedef_type.spelling:
    return False

  # error: 'NCollection_UBTree' is not a class, namespace, or enumeration
  if typedef.spelling in [
    "BRepBuilderAPI_BndBoxTree",
    "Extrema_UBTreeOfSphere",
    "ShapeAnalysis_BoxBndTree",
    "BRepClass3d_BndBoxTree"
  ]:
    return False

  # error: 'NCollection_CellFilter' is not a class, namespace, or enumeration
  if typedef.spelling in [
    "BRepBuilderAPI_CellFilter"
  ]:
    return False

  # error: 'NCollection_CellFilter' is not a class, namespace, or enumeration
  if typedef.spelling in [
    "BRepBuilderAPI_CellFilter"
  ]:
    return False

  # error during instantiation: Uncaught (in promise) BindingError: Cannot register type 'IntSurf_Allocator' twice
  if typedef.spelling in [
    "IntSurf_Allocator"
  ]:
    return False

  # error during instantiation: Uncaught (in promise) BindingError: Cannot register type 'TDF_HAllocator' twice
  if typedef.spelling in [
    "TDF_HAllocator"
  ]:
    return False

  # RuntimeError: function signature mismatch when calling STEPCAFontrol_Reader.ReadFile()
  if typedef.spelling == "Interface_VectorOfFileParameter":
    return False

  # error: no template named 'handle'; did you mean 'opencascade::handle'?
  if typedef.spelling in [
    "Handle_StepKinematics_UnconstrainedPair",
    "Handle_StepKinematics_UnconstrainedPairValue"
  ]:
    return False

  # BindingError: Cannot register type 'gp_Vec2f' twice / BindingError: Cannot register type 'gp_Vec3f' twice / ...
  if typedef.spelling in [
    "Graphic3d_Vec2",
    "Graphic3d_Vec3",
  ]:
    return False

  # error: cannot initialize a parameter of type 'Standard_Transient *' with an lvalue of type 'math_NotSquare *'
  if typedef.spelling in [
    "Handle_math_NotSquare",
    "Handle_math_SingularMatrix",
  ]:
    return False

  # error: no matching function for call to 'select_overload' (item type is void *)
  if typedef.spelling in [
    "BRepClass3d_MapOfInter",
    "TColStd_SequenceOfAddress",
    "TopTools_IndexedDataMapOfShapeAddress",
  ]:
    return False

  if typedef.location.file.name == "myMain.h" or typedef.underlying_typedef_type.spelling.startswith((
    "opencascade::handle",
    "handle",
    "NCollection"
  )):
    return True

  return False
