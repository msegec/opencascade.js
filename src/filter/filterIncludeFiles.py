def filterIncludeFile(filename):
  if not filename.endswith(".hxx"):
    return False

  # fatal error: 'X11/Shell.h' file not found
  if filename == "IVtkDraw_Interactor.hxx":
    return False

  # fatal error: 'vtkType.h' file not found
  if (
    filename == "IVtk_Types.hxx" or
    filename == "IVtk_IShape.hxx" or
    filename == "IVtk_IShapeData.hxx" or
    filename == "IVtk_IShapeMesher.hxx" or
    filename == "IVtk_IShapePickerAlgo.hxx" or
    filename == "IVtkOCC_SelectableObject.hxx" or
    filename == "IVtkOCC_Shape.hxx" or
    filename == "IVtkOCC_ShapeMesher.hxx" or
    filename == "IVtkOCC_ShapePickerAlgo.hxx" or
    filename == "IVtk_IShapePickerAlgo.hxx" or
    filename == "IVtkTools.hxx" or
    filename == "IVtkTools_DisplayModeFilter.hxx" or
    filename == "IVtkTools_ShapeDataSource.hxx" or
    filename == "IVtkTools_ShapeObject.hxx" or
    filename == "IVtkTools_ShapePicker.hxx" or
    filename == "IVtkTools_SubPolyDataFilter.hxx" or
    filename == "IVtkVTK_ShapeData.hxx"
  ):
    return False

  # fatal error: 'vtkSmartPointer.h' file not found 
  if (
    filename == "IVtkVTK_View.hxx"
  ):
    return False

  # fatal error: 'windows.h' file not found 
  if (
    filename == "OSD_WNT.hxx" or
    filename == "WNT_Dword.hxx"
  ):
    return False

  # fatal error: 'vtkActor.h' file not found
  if filename == "IVtkDraw_HighlightAndSelectionPipeline.hxx":
    return False

  # error: typedef redefinition with different types (GL_APIENTRY undefined; no OCCT file includes this header)
  if filename == "OpenGl_GLESExtensions.hxx":
    return False

  # error: no member named 'NbIterations' in 'MathLin::EigenResult' (MathLin_EigenSearch.hxx shadows MathUtils::EigenResult; only one .cxx includes this header)
  if filename == "MathLin_Jacobi.hxx":
    return False

  # fatal error: 'BOPDS_ListOfPaveBlock.hxx' file not found (also Graphic3d_MapOfStructure.hxx, TObj_SequenceOfObject.hxx; OCCT 8 deprecated aliases for removed headers)
  if filename in [
    "BOPDS_DataMapOfIntegerListOfPaveBlock.hxx",
    "BOPDS_DataMapOfPaveBlockListOfPaveBlock.hxx",
    "BOPDS_IndexedDataMapOfPaveBlockListOfPaveBlock.hxx",
    "BOPDS_VectorOfListOfPaveBlock.hxx",
    "Graphic3d_MapIteratorOfMapOfStructure.hxx",
    "TObj_Container.hxx",
  ]:
    return False

  return True
