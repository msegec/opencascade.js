#!/usr/bin/python3

import os
from Common import includeFlags, compileFlags
from preamble import preamblePath
import subprocess
import multiprocessing
from functools import partial

from argparse import ArgumentParser

libraryBasePath = "/opencascade.js/build/bindings"

def buildOneFile(command, item):
  print("building " + item)
  subprocess.check_call([*command, "-c", item, "-o", item + ".o"])

def compileBindings(root, threading):
  filesToBuild = []
  for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [x for x in dirnames if not os.path.exists(preamblePath(dirpath + "/" + x))]
    filesToBuild.extend(dirpath + "/" + x for x in filenames if x.endswith(".cpp") and not os.path.exists(dirpath + "/" + x + ".o"))
  if len(filesToBuild) == 0:
    return

  command = [
    "emcc",
    *compileFlags(threading),
    *includeFlags(),
  ]
  pch = preamblePath(root) + "." + threading + ".pch"
  print("building " + pch)
  subprocess.check_call([*command, "-x", "c++-header", preamblePath(root), "-o", pch])
  try:
    with multiprocessing.Pool() as p:
      p.map(partial(buildOneFile, [*command, "-include-pch", pch]), sorted(filesToBuild))
  finally:
    os.remove(pch)

def compileCustomCodeBindings(args):
  compileBindings(libraryBasePath + "/myMain.h", args["threading"])

if __name__ == "__main__":
  parser = ArgumentParser()
  parser.add_argument(dest="threading", choices=["single-threaded", "multi-threaded"], help="Build in single vs. multi-threaded mode")
  args = parser.parse_args()

  compileBindings(libraryBasePath, args.threading)
