#!/usr/bin/python3

import os
import re
import subprocess
import multiprocessing
from Common import compileFlags, includeFlags

from filter.filterSourceFiles import filterSourceFile
from filter.filterPackages import filterPackages

from argparse import ArgumentParser

libraryBasePath = "/opencascade.js/build/sources"

# Potentially problematic packages, when used with dynamic linking
# These files contain function pointer definitions and header files and are therefore likely to cause problems.
# https://github.com/emscripten-core/emscripten/issues/13241
# "AdvApp2Var"
# "BRepGProp"
# "BRepMesh"
# "BSplSLib"
# "CPnts"
# "DDF"
# "Draw"
# "Graphic3d"
# "IFSelect"
# "Interface"
# "MoniTool"
# "NCollection"
# "OpenGl"
# "OSD"
# "ShapeProcess"
# "Standard"
# "StdObjMgt"
# "TDF

sourceBasePath = "/occt/src/"

def buildObjectFiles(file, args):
  relativeFile = file.replace(sourceBasePath, "")
  os.makedirs(libraryBasePath + "/" + os.path.dirname(relativeFile), exist_ok=True)
  command = [
    "emcc",
    *compileFlags(args["threading"]),
    *includeFlags(),
    "-c",
    file,
  ]

  if not os.path.exists(libraryBasePath + "/" + relativeFile + ".o"):
    print("Building " + relativeFile)
    subprocess.check_call([
      *command,
      "-o", libraryBasePath + "/" + relativeFile + ".o",
      ])
  else:
    print(relativeFile + ".o already exists, skipping")

allModules = {}
for dirpath, dirnames, filenames in os.walk(sourceBasePath):
  if not "PACKAGES.cmake" in filenames:
    continue
  with open(dirpath + "/PACKAGES.cmake", "r") as a_file:
    allModules[os.path.basename(dirpath)] = [os.path.basename(x) for x in re.findall(r"^\s+([\w./]+)\s*$", a_file.read(), re.MULTILINE)]
def getModuleNameByPackageName(inputPackageName):
  for moduleName in allModules:
    for package in allModules[moduleName]:
      packageName = package.strip()
      if packageName == inputPackageName:
        return moduleName
  return ""

filesToBuild = []
for dirpath, dirnames, filenames in os.walk(sourceBasePath):
  packageOrModuleName = os.path.basename(dirpath.replace(sourceBasePath, ""))
  for item in filenames:
    if not filterPackages(packageOrModuleName) or not filterPackages(getModuleNameByPackageName(packageOrModuleName)):
      continue
    if filterSourceFile(dirpath + "/" + item):
      filesToBuild.append(dirpath + "/" + item)

if __name__ == "__main__":
  parser = ArgumentParser()
  parser.add_argument(dest="threading", choices=["single-threaded", "multi-threaded"], help="Build in single vs. multi-threaded mode")
  args = parser.parse_args()

  os.makedirs(libraryBasePath, exist_ok=True)

  def myBuildFunction(x):
    buildObjectFiles(x, {
      "threading": args.threading,
    })

  with multiprocessing.Pool(processes=multiprocessing.cpu_count()) as p:
    p.map(myBuildFunction, filesToBuild)
