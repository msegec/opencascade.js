#!/usr/bin/python3

import os
import re
import subprocess
import json
from itertools import chain
import yaml
from generateBindings import generateCustomCodeBindings
from compileBindings import compileCustomCodeBindings
import shutil
from cerberus import Validator
from argparse import ArgumentParser
from Common import includeFlags, compileFlags, threadingFlags
from customBuildSchema import schema

libraryBasePath = "/opencascade.js/build"

def walkFiles(root):
  return sorted(dirpath + "/" + item for dirpath, dirnames, filenames in os.walk(root) for item in filenames)

def verifyBindings(bindings, builtSymbols) -> None:
  for binding in bindings:
    if not binding["symbol"] in builtSymbols:
      raise Exception("Requested binding " + json.dumps(binding) + " does not exist!")

def shouldProcessSymbol(symbol: str, bindings) -> bool:
  if len(bindings) == 0:
    return True
  entry = next((b for b in bindings if b["symbol"] == symbol), None)
  if not entry is None:
    return True
  return False

def runBuild(build, bindingFiles):
  def getAdditionalBindCodeO():
    if "additionalBindCode" in build:
      os.makedirs(libraryBasePath + "/additionalBindCode", exist_ok=True)
      additionalBindCodeFileName = libraryBasePath + "/additionalBindCode/" + build["name"] + ".cpp"
      f = open(additionalBindCodeFileName, "w")
      f.write(build["additionalBindCode"])
      f.close()
      print("building " + additionalBindCodeFileName)
      command = [
        "emcc",
        *compileFlags(os.environ["threading"]),
        *includeFlags(),
        "-c", additionalBindCodeFileName,
      ]
      subprocess.check_call([
        *command,
        "-o", additionalBindCodeFileName + ".o",
      ])
      return additionalBindCodeFileName + ".o"
    else:
      return None
  additionalBindCodeO = getAdditionalBindCodeO()
  print("Running build: " + build["name"])
  bindingsO = [x for x in bindingFiles if x.endswith(".cpp.o") and shouldProcessSymbol(os.path.basename(x)[:-6], build["bindings"])]
  sourcesO = [x for x in walkFiles(libraryBasePath + "/sources") if x.endswith(".o") and not os.path.basename(x) in [
    "XBRepMesh.o",
  ]]
  subprocess.check_call([
    "em++", "-lembind", *([] if additionalBindCodeO is None else [additionalBindCodeO]),
    *bindingsO, *sourcesO,
    "-o", os.getcwd() + "/" + build["name"],
    *threadingFlags(os.environ["threading"]),
    *build["emccFlags"],
  ])
  print("Build finished")

def writeTypescriptDefinitions(typescriptDefinitions, mainBuildName):
  typescriptDefinitionOutput = ""
  typescriptExports = []
  for dts in typescriptDefinitions:
    typescriptDefinitionOutput += re.sub(r"NCollection_DefaultHasher<[^<>]*>", "any", dts[".d.ts"])
    for export in dts["exports"]:
      typescriptExports.append({
        "export": export,
        "kind": dts["kind"],
      })

  typescriptDefinitionOutput += \
    "type Standard_Boolean = boolean;\n" + \
    "type Standard_Byte = number;\n" + \
    "type Standard_Character = number;\n" + \
    "type Standard_CString = string;\n" + \
    "type Standard_Integer = number;\n" + \
    "type Standard_Real = number;\n" + \
    "type Standard_ShortReal = number;\n" + \
    "type Standard_Size = number;\n\n" + \
    "declare namespace FS {\n" + \
    "  interface Lookup {\n" + \
    "      path: string;\n" + \
    "      node: FSNode;\n" + \
    "  }\n" + \
    "\n" + \
    "  interface FSStream {}\n" + \
    "  interface FSNode {}\n" + \
    "  interface ErrnoError {}\n" + \
    "\n" + \
    "  let ignorePermissions: boolean;\n" + \
    "  let trackingDelegate: any;\n" + \
    "  let tracking: any;\n" + \
    "  let genericErrors: any;\n" + \
    "\n" + \
    "  //\n" + \
    "  // paths\n" + \
    "  //\n" + \
    "  function lookupPath(path: string, opts: any): Lookup;\n" + \
    "  function getPath(node: FSNode): string;\n" + \
    "\n" + \
    "  //\n" + \
    "  // nodes\n" + \
    "  //\n" + \
    "  function isFile(mode: number): boolean;\n" + \
    "  function isDir(mode: number): boolean;\n" + \
    "  function isLink(mode: number): boolean;\n" + \
    "  function isChrdev(mode: number): boolean;\n" + \
    "  function isBlkdev(mode: number): boolean;\n" + \
    "  function isFIFO(mode: number): boolean;\n" + \
    "  function isSocket(mode: number): boolean;\n" + \
    "\n" + \
    "  //\n" + \
    "  // devices\n" + \
    "  //\n" + \
    "  function major(dev: number): number;\n" + \
    "  function minor(dev: number): number;\n" + \
    "  function makedev(ma: number, mi: number): number;\n" + \
    "  function registerDevice(dev: number, ops: any): void;\n" + \
    "\n" + \
    "  //\n" + \
    "  // core\n" + \
    "  //\n" + \
    "  function syncfs(populate: boolean, callback: (e: any) => any): void;\n" + \
    "  function syncfs(callback: (e: any) => any, populate?: boolean): void;\n" + \
    "  function mount(type: any, opts: any, mountpoint: string): any;\n" + \
    "  function unmount(mountpoint: string): void;\n" + \
    "\n" + \
    "  function mkdir(path: string, mode?: number): any;\n" + \
    "  function mkdev(path: string, mode?: number, dev?: number): any;\n" + \
    "  function symlink(oldpath: string, newpath: string): any;\n" + \
    "  function rename(old_path: string, new_path: string): void;\n" + \
    "  function rmdir(path: string): void;\n" + \
    "  function readdir(path: string): any;\n" + \
    "  function unlink(path: string): void;\n" + \
    "  function readlink(path: string): string;\n" + \
    "  function stat(path: string, dontFollow?: boolean): any;\n" + \
    "  function lstat(path: string): any;\n" + \
    "  function chmod(path: string, mode: number, dontFollow?: boolean): void;\n" + \
    "  function lchmod(path: string, mode: number): void;\n" + \
    "  function fchmod(fd: number, mode: number): void;\n" + \
    "  function chown(path: string, uid: number, gid: number, dontFollow?: boolean): void;\n" + \
    "  function lchown(path: string, uid: number, gid: number): void;\n" + \
    "  function fchown(fd: number, uid: number, gid: number): void;\n" + \
    "  function truncate(path: string, len: number): void;\n" + \
    "  function ftruncate(fd: number, len: number): void;\n" + \
    "  function utime(path: string, atime: number, mtime: number): void;\n" + \
    "  function open(path: string, flags: string, mode?: number, fd_start?: number, fd_end?: number): FSStream;\n" + \
    "  function close(stream: FSStream): void;\n" + \
    "  function llseek(stream: FSStream, offset: number, whence: number): any;\n" + \
    "  function read(stream: FSStream, buffer: ArrayBufferView, offset: number, length: number, position?: number): number;\n" + \
    "  function write(\n" + \
    "      stream: FSStream,\n" + \
    "      buffer: ArrayBufferView,\n" + \
    "      offset: number,\n" + \
    "      length: number,\n" + \
    "      position?: number,\n" + \
    "      canOwn?: boolean,\n" + \
    "  ): number;\n" + \
    "  function allocate(stream: FSStream, offset: number, length: number): void;\n" + \
    "  function mmap(\n" + \
    "      stream: FSStream,\n" + \
    "      buffer: ArrayBufferView,\n" + \
    "      offset: number,\n" + \
    "      length: number,\n" + \
    "      position: number,\n" + \
    "      prot: number,\n" + \
    "      flags: number,\n" + \
    "  ): any;\n" + \
    "  function ioctl(stream: FSStream, cmd: any, arg: any): any;\n" + \
    "  function readFile(path: string, opts: { encoding: 'binary'; flags?: string }): Uint8Array;\n" + \
    "  function readFile(path: string, opts: { encoding: 'utf8'; flags?: string }): string;\n" + \
    "  function readFile(path: string, opts?: { flags?: string }): Uint8Array;\n" + \
    "  function writeFile(path: string, data: string | ArrayBufferView, opts?: { flags?: string }): void;\n" + \
    "\n" + \
    "  //\n" + \
    "  // module-level FS code\n" + \
    "  //\n" + \
    "  function cwd(): string;\n" + \
    "  function chdir(path: string): void;\n" + \
    "  function init(\n" + \
    "      input: null | (() => number | null),\n" + \
    "      output: null | ((c: number) => any),\n" + \
    "      error: null | ((c: number) => any),\n" + \
    "  ): void;\n" + \
    "\n" + \
    "  function createLazyFile(\n" + \
    "      parent: string | FSNode,\n" + \
    "      name: string,\n" + \
    "      url: string,\n" + \
    "      canRead: boolean,\n" + \
    "      canWrite: boolean,\n" + \
    "  ): FSNode;\n" + \
    "  function createPreloadedFile(\n" + \
    "      parent: string | FSNode,\n" + \
    "      name: string,\n" + \
    "      url: string,\n" + \
    "      canRead: boolean,\n" + \
    "      canWrite: boolean,\n" + \
    "      onload?: () => void,\n" + \
    "      onerror?: () => void,\n" + \
    "      dontCreateFile?: boolean,\n" + \
    "      canOwn?: boolean,\n" + \
    "  ): void;\n" + \
    "  function createDataFile(\n" + \
    "      parent: string | FSNode,\n" + \
    "      name: string,\n" + \
    "      data: ArrayBufferView | string,\n" + \
    "      canRead: boolean,\n" + \
    "      canWrite: boolean,\n" + \
    "      canOwn: boolean,\n" + \
    "  ): FSNode;\n" + \
    "  interface AnalysisResults {\n" + \
    "    isRoot: boolean,\n" + \
    "    exists: boolean,\n" + \
    "    error: Error,\n" + \
    "    name: string,\n" + \
    "    path: any,\n" + \
    "    object: any,\n" + \
    "    parentExists: boolean,\n" + \
    "    parentPath: any,\n" + \
    "    parentObject: any\n" + \
    "  }\n" + \
    "  function analyzePath(path: string): AnalysisResults;\n" + \
    "}\n\n" + \
    "\nexport type OpenCascadeInstance = {FS: typeof FS} & {\n  " + ";\n  ".join(map(lambda x: x["export"] + ((": typeof " + x["export"]) if x["kind"] == "class" else (": " + x["export"])), typescriptExports)) + ";\n" + \
    "};\n\n" + \
    "declare function init(): Promise<OpenCascadeInstance>;\n\n" + \
    "export default init;\n"

  with open(os.getcwd() + "/" + os.path.splitext(mainBuildName)[0] + ".d.ts", "w") as f:
    f.write(typescriptDefinitionOutput)

if __name__ == "__main__":
  parser = ArgumentParser()
  parser.add_argument(dest="filename", help="Custom build input file (.yml)", metavar="FILE.yml")
  args = parser.parse_args()

  with open(args.filename, "r") as f:
    buildConfig = yaml.safe_load(f)
  v = Validator(schema)
  if not v.validate(buildConfig, schema):
    raise Exception(v.errors)
  buildConfig = v.normalized(buildConfig)

  customBindingsPath = libraryBasePath + "/bindings/myMain.h"
  if os.path.exists(customBindingsPath):
    shutil.rmtree(customBindingsPath)

  if buildConfig["additionalCppCode"]:
    generateCustomCodeBindings(buildConfig["additionalCppCode"])
    compileCustomCodeBindings({
      "threading": os.environ['threading'],
    })

  bindingFiles = walkFiles(libraryBasePath + "/bindings")
  builtSymbols = set(os.path.basename(x)[:-6] for x in bindingFiles if x.endswith(".cpp.o"))
  builds = [buildConfig["mainBuild"], *buildConfig["extraBuilds"]]
  for build in builds:
    verifyBindings(build["bindings"], builtSymbols)

  for build in builds:
    runBuild(build, bindingFiles)

  if buildConfig["generateTypescriptDefinitions"]:
    requestedBindings = list(chain(*(build["bindings"] for build in builds)))
    typescriptDefinitions = []
    for file in bindingFiles:
      item = os.path.basename(file)
      if item.endswith(".d.ts.json") and shouldProcessSymbol(item[:-10], requestedBindings):
        with open(file, "r") as f:
          typescriptDefinitions.append(json.loads(f.read()))
    writeTypescriptDefinitions(typescriptDefinitions, buildConfig["mainBuild"]["name"])
