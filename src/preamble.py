import os

def preamblePath(root):
  return root + "/preamble.hxx"

def writePreamble(root, text):
  os.makedirs(root, exist_ok=True)
  with open(preamblePath(root), "w") as f:
    f.write("#pragma once\n" + text)
  return "#include \"" + preamblePath(root) + "\"\n"
