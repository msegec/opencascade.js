#!/usr/bin/python3

from typing import Callable
from bindings import EmbindBindings, TypescriptBindings, shouldProcessClass, normalizeSpelling
import clang.cindex
import os
import errno
from filter.filterTypedefs import filterTypedef
from filter.filterEnums import filterEnum
from wasmGenerator.Common import ignoreDuplicateTypedef, SkipException
from Common import occtHeaders, clangIncludeFlags
from preamble import writePreamble
import json
import multiprocessing
import os
from filter.filterPackages import filterPackages
from functools import partial, lru_cache

libraryBasePath = "/opencascade.js/build/bindings"
buildDirectory = "/opencascade.js/build"
occtBasePath = "/occt/src/"
ocIncludeStatements = os.linesep.join(map(lambda x: "#include \"" + os.path.basename(x) + "\"", list(sorted(occtHeaders()))))
handleTypedefsFile = occtBasePath + "Handle_Typedefs.hxx"

def mkdirp(name: str) -> None:
  try:
    os.makedirs(name)
  except OSError as e:
    if e.errno != errno.EEXIST:
      raise

def filterClasses(child, customBuild):
  if customBuild:
    return (
      child.location.file.name == "myMain.h" and
      shouldProcessClass(child, occtBasePath)
    )
  return (
    child.extent.start.file.name.startswith(occtBasePath) and
    filterPackages(os.path.basename(os.path.dirname(child.location.file.name))) and
    shouldProcessClass(child, occtBasePath)
  )

def filterTemplates(child, customBuild):
  if customBuild:
    return (
      child.location.file.name == "myMain.h" and
      child.kind == clang.cindex.CursorKind.TYPEDEF_DECL and
      (
        child.underlying_typedef_type.kind == clang.cindex.TypeKind.ELABORATED or
        child.underlying_typedef_type.kind == clang.cindex.TypeKind.UNEXPOSED
      )
    )
  return ((
      child.extent.start.file.name.startswith(occtBasePath) and
      filterPackages(os.path.basename(os.path.dirname(child.location.file.name)))
    ) and
    child.kind == clang.cindex.CursorKind.TYPEDEF_DECL and
    (
      child.underlying_typedef_type.kind == clang.cindex.TypeKind.ELABORATED or
      child.underlying_typedef_type.kind == clang.cindex.TypeKind.UNEXPOSED
    )
  )

def filterEnums(child, customBuild):
  if customBuild:
    return child.location.file.name == "myMain.h"
  return ((
      child.extent.start.file.name.startswith(occtBasePath) and
      filterPackages(os.path.basename(os.path.dirname(child.location.file.name)))
    ) and
    child.kind == clang.cindex.CursorKind.ENUM_DECL
  )

def processChildBatch(customCode, generator, buildType: str, extension: str, filterFunction: Callable[[any], bool], processFunction: Callable[[any, any], str], typedefGenerator: any, templateTypedefGenerator: any, preamble: str, customBuild: bool, batch):
  tu = parse(customCode)
  children = generator(tu)[batch.start:batch.stop]

  for child in children:
    if not filterFunction(child, customBuild) or child.spelling == "":
      continue

    relOcFileName: str = child.extent.start.file.name.replace(occtBasePath, "")
    mkdirp(buildDirectory + "/" + buildType + "/" + os.path.dirname(relOcFileName))
    mkdirp(buildDirectory + "/" + buildType + "/" + relOcFileName)
    filename = buildDirectory + "/" + buildType + "/" + relOcFileName + "/" + (child.spelling if not child.spelling == "" else child.type.spelling) + extension

    if not os.path.exists(filename):
      print("Processing " + child.spelling)
      try:
        output = processFunction(tu, preamble, child, typedefGenerator(tu), templateTypedefGenerator(tu))
        bindingsFile = open(filename, "w")
        bindingsFile.write(output)
      except SkipException as e:
        print(str(e))
    else:
      print("file " + child.spelling + ".cpp already exists, skipping")

def split(a, n):
  k, m = divmod(len(a), n)
  return (a[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in range(n))

def processChildren(generator, buildType: str, extension: str, filterFunction: Callable[[any], bool], processFunction: Callable[[any, any], str], typedefs: any, templateTypedefs: any, preamble: str, customCode, customBuild):
  tu = parse(customCode)
  func = partial(processChildBatch, customCode, generator, buildType, extension, filterFunction, processFunction, typedefs, templateTypedefs, preamble, customBuild)
  if not customBuild:
    numthreads = multiprocessing.cpu_count()
    batches = split(range(len(generator(tu))), numthreads)
    with multiprocessing.Pool(processes=numthreads) as p:
      p.map(func, batches)
  else:
    func(range(len(generator(tu))))

def processTemplate(child):
  templateRefs = list(filter(lambda x: x.kind == clang.cindex.CursorKind.TEMPLATE_REF, child.get_children()))
  if len(templateRefs) != 1:
    raise SkipException("The number of template refs for the template typedef \"" + child.spelling + "\" is not 1!")

  templateClass = templateRefs[0].get_definition()
  if templateClass is None:
    raise SkipException("Template class is None (" + child.spelling + ")")
  templateArgNames = list(filter(lambda x: x.kind == clang.cindex.CursorKind.TEMPLATE_TYPE_PARAMETER, templateClass.get_children()))
  templateArgs = {}
  for i, templateArgName in enumerate(templateArgNames):
    templateArgType = child.type.get_template_argument_type(i)
    if templateArgType.spelling == "":
      templateArgType = child.type.get_canonical().get_template_argument_type(i)
    if templateArgType.spelling == "":
      raise SkipException("Template argument type is empty for at least one argument (" + child.spelling + ")")
    templateArgs[templateArgName.spelling] = templateArgType
  
  return [templateClass, templateArgs]

def embindGenerationFuncClasses(tu, preamble, child, typedefs, templateTypedefs) -> str:
  embindings = EmbindBindings(typedefs, templateTypedefs, tu)
  output = embindings.processClass(child)

  return preamble + output

def embindGenerationFuncTemplates(tu, preamble, child, typedefs, templateTypedefs) -> str:
  [templateClass, templateArgs] = processTemplate(child)
  embindings = EmbindBindings(typedefs, templateTypedefs, tu)
  output = embindings.processClass(templateClass, child, templateArgs)

  return preamble + output

def embindGenerationFuncEnums(tu, preamble, child, typedefs, templateTypedefs) -> str:
  embindings = EmbindBindings(typedefs, templateTypedefs, tu)
  output = embindings.processEnum(child)

  return preamble + output

@lru_cache(maxsize=1)
def templateTypedefGenerator(tu):
  return list(filter(
    lambda x:
      x.kind == clang.cindex.CursorKind.TYPEDEF_DECL and
      not (x.get_definition() is None or not x == x.get_definition()) and
      filterTypedef(x) and
      x.type.get_num_template_arguments() != -1 and
      not ignoreDuplicateTypedef(x),
    tu.cursor.get_children()))

@lru_cache(maxsize=1)
def typedefGenerator(tu):
  typedefs = {}
  occtTypedefs = [x for x in tu.cursor.get_children() if x.kind == clang.cindex.CursorKind.TYPEDEF_DECL and x.location.file.name.startswith(occtBasePath)]
  for x in sorted(occtTypedefs, key=lambda x: x.location.file.name != handleTypedefsFile):
    typedefs.setdefault(normalizeSpelling(x.underlying_typedef_type.spelling), x.spelling)
  return typedefs

def allChildrenGenerator(tu):
  return list(tu.cursor.get_children())

def enumGenerator(tu):
  return list(filter(lambda x: x.kind == clang.cindex.CursorKind.ENUM_DECL and filterEnum(x), tu.cursor.get_children()))

def process(extension, embindGenerationFuncClasses, embindGenerationFuncTemplates, embindGenerationFuncEnums, preamble, customCode, customBuild):
  processChildren(allChildrenGenerator, "bindings", extension, filterClasses, embindGenerationFuncClasses, typedefGenerator, templateTypedefGenerator, preamble, customCode, customBuild)
  processChildren(templateTypedefGenerator, "bindings", extension, filterTemplates, embindGenerationFuncTemplates, typedefGenerator, templateTypedefGenerator, preamble, customCode, customBuild)
  processChildren(enumGenerator, "bindings", extension, filterEnums, embindGenerationFuncEnums, typedefGenerator, templateTypedefGenerator, preamble, customCode, customBuild)

def typescriptGenerationFuncClasses(tu, preamble, child, typedefs, templateTypedefs) -> str:
  typescript = TypescriptBindings(typedefs, templateTypedefs, tu)
  output = typescript.processClass(child)

  return json.dumps({
    ".d.ts": preamble + output,
    "kind": "class",
    "exports": typescript.exports,
  })

def typescriptGenerationFuncTemplates(tu, preamble, child, typedefs, templateTypedefs) -> str:
  [templateClass, templateArgs] = processTemplate(child)
  typescript = TypescriptBindings(typedefs, templateTypedefs, tu)
  output = typescript.processClass(templateClass, child, templateArgs)

  return json.dumps({
    ".d.ts": preamble + output,
    "kind": "class",
    "exports": typescript.exports,
  })

def typescriptGenerationFuncEnums(tu, preamble, child, typedefs, templateTypedefs) -> str:
  typescript = TypescriptBindings(typedefs, templateTypedefs, tu)
  output = typescript.processEnum(child)

  return json.dumps({
    ".d.ts": preamble + output,
    "kind": "enum",
    "exports": typescript.exports,
  })

def parseFiles(files):
  translationUnit = clang.cindex.Index.create().parse(
    "myMain.h", [
      "-x",
      "c++",
      "-stdlib=libc++",
      "-D__EMSCRIPTEN__",
      "-DOCCT_NO_DEPRECATED",
    ] + clangIncludeFlags(),
    files
  )

  if len(translationUnit.diagnostics) > 0:
    print("Diagnostic Messages:")
    for d in translationUnit.diagnostics:
      print("  " + d.format())

  errors = [d.format() for d in translationUnit.diagnostics if d.severity >= clang.cindex.Diagnostic.Error]
  if errors:
    raise Exception("Clang reported " + str(len(errors)) + " error diagnostic(s) while parsing:\n  " + "\n  ".join(errors))

  return translationUnit

def isTransient(theClass, known):
  if theClass.spelling not in known:
    known[theClass.spelling] = theClass.spelling == "Standard_Transient" or any(
      isTransient(x.type.get_declaration().get_definition() or x.type.get_declaration(), known)
      for x in theClass.get_children()
      if x.kind == clang.cindex.CursorKind.CXX_BASE_SPECIFIER
    )
  return known[theClass.spelling]

@lru_cache(maxsize=1)
def handleTypedefs():
  tu = parseFiles([["myMain.h", ocIncludeStatements]])
  children = list(tu.cursor.get_children())
  existing = set(x.spelling for x in children if x.kind == clang.cindex.CursorKind.TYPEDEF_DECL)
  known = {}
  names = [
    x.spelling for x in children
    if x.kind in [clang.cindex.CursorKind.CLASS_DECL, clang.cindex.CursorKind.STRUCT_DECL] and
    x.is_definition() and
    x.location.file.name.startswith(occtBasePath) and
    filterPackages(os.path.basename(os.path.dirname(x.location.file.name))) and
    not "Handle_" + x.spelling in existing and
    isTransient(x, known)
  ]
  return "".join(map(lambda x: "typedef opencascade::handle<" + x + "> Handle_" + x + ";\n", dict.fromkeys(names)))

@lru_cache(maxsize=1)
def parse(additionalCppCode = ""):
  return parseFiles([
    ["myMain.h", ocIncludeStatements + "\n#include \"" + handleTypedefsFile + "\"\n" + additionalCppCode],
    [handleTypedefsFile, handleTypedefs()],
  ])

referenceTypeTemplateDefs = \
  "\n" + \
  "#include <emscripten/bind.h>\n" + \
  "using namespace emscripten;\n" + \
  "#include <functional>\n" + \
  "\n" + \
  "template<typename T>\n" + \
  "T getReferenceValue(const emscripten::val& v) {\n" + \
  "  if(!(v.typeOf().as<std::string>() == \"object\")) {\n" + \
  "    return v.as<T>(allow_raw_pointers());\n" + \
  "  } else if(v.hasOwnProperty(\"current\")) {\n" + \
  "    return v[\"current\"].as<T>(allow_raw_pointers());\n" + \
  "  }\n" + \
  "  emscripten::val::global(\"TypeError\").new_(std::string(\"unsupported type\")).throw_();\n" + \
  "}\n" + \
  "\n" + \
  "template<typename T>\n" + \
  "void updateReferenceValue(emscripten::val& v, T& val) {\n" + \
  "  if(v.typeOf().as<std::string>() == \"object\" && v.hasOwnProperty(\"current\")) {\n" + \
  "    v.set(\"current\", val, allow_raw_pointers());\n" + \
  "  }\n" + \
  "}\n" + \
  "\n"

def generateCustomCodeBindings(customCode):
  embindPreamble = writePreamble(libraryBasePath + "/myMain.h", ocIncludeStatements + "\n" + handleTypedefs() + referenceTypeTemplateDefs + "\n" + customCode)

  process(".cpp", embindGenerationFuncClasses, embindGenerationFuncTemplates, embindGenerationFuncEnums, embindPreamble, customCode, True)
  process(".d.ts.json", typescriptGenerationFuncClasses, typescriptGenerationFuncTemplates, typescriptGenerationFuncEnums, "", customCode, True)

if __name__ == "__main__":
  embindPreamble = writePreamble(libraryBasePath, ocIncludeStatements + "\n" + handleTypedefs() + referenceTypeTemplateDefs)
  process(".cpp", embindGenerationFuncClasses, embindGenerationFuncTemplates, embindGenerationFuncEnums, embindPreamble, "", False)

  process(".d.ts.json", typescriptGenerationFuncClasses, typescriptGenerationFuncTemplates, typescriptGenerationFuncEnums, "", "", False)
