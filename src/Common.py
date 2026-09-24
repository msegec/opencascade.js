from filter.filterIncludeFiles import filterIncludeFile
from typing import Set
import os

occtBasePath = "/occt/src/"

codegenFlags = [
  "-flto",
  "-fwasm-exceptions",
  "-O3",
]

def threadingFlags(threading):
  return ["-pthread"] if threading == "multi-threaded" else []

def compileFlags(threading):
  return [
    *codegenFlags,
    "-DOCCT_NO_PLUGINS",
    "-DOCCT_NO_DEPRECATED",
    "-frtti",
    "-DHAVE_RAPIDJSON",
    *threadingFlags(threading),
  ]

def getGlobalIncludes() -> Set[str]:
  includeFiles = list()
  additionalIncludePaths = list()
  for dirpath, dirnames, filenames in os.walk(occtBasePath):
    dirnames[:] = [x for x in dirnames if x != "GTests"]
    additionalIncludePaths.append(str(dirpath))
    for item in filenames:
      if filterIncludeFile(item):
        includeFiles.append(str(os.path.join(dirpath, item)))
  return [includeFiles, additionalIncludePaths]

[ocIncludeFiles, ocIncludePaths] = getGlobalIncludes()

additionalIncludePaths = [
  "/rapidjson/include",
]

includePathArgs = \
  list(dict.fromkeys(map(lambda x: "-I" + x, ocIncludePaths))) + \
  list(map(lambda x: "-I" + x, [
    "/emsdk/upstream/emscripten/cache/sysroot/include/compat/",
    "/emsdk/upstream/emscripten/cache/sysroot/include/c++/v1/",
    "/emsdk/upstream/lib/clang/" + next(os.walk('/emsdk/upstream/lib/clang/'))[1][0] + "/include/",
    "/emsdk/upstream/emscripten/cache/sysroot/include/",
  ])) + \
  list(map(lambda x: "-I" + x, ocIncludePaths + additionalIncludePaths))
  