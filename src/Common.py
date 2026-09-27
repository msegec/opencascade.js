from filter.filterIncludeFiles import filterIncludeFile
from functools import cache
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

@cache
def occtHeadersAndDirs():
  headers = []
  dirs = []
  for dirpath, dirnames, filenames in os.walk(occtBasePath):
    dirnames[:] = [x for x in dirnames if x != "GTests"]
    dirs.append(dirpath)
    headers.extend(os.path.join(dirpath, x) for x in filenames if filterIncludeFile(x))
  return headers, dirs

def occtHeaders():
  return occtHeadersAndDirs()[0]

def includeFlags():
  return ["-I" + x for x in occtHeadersAndDirs()[1] + ["/rapidjson/include"]]

@cache
def clangIncludeFlags():
  clangVersion = next(os.walk("/emsdk/upstream/lib/clang/"))[1][0]
  return \
    list(dict.fromkeys("-I" + x for x in occtHeadersAndDirs()[1])) + \
    ["-I" + x for x in [
      "/emsdk/upstream/emscripten/cache/sysroot/include/compat/",
      "/emsdk/upstream/emscripten/cache/sysroot/include/c++/v1/",
      "/emsdk/upstream/lib/clang/" + clangVersion + "/include/",
      "/emsdk/upstream/emscripten/cache/sysroot/include/",
    ]] + \
    includeFlags()
