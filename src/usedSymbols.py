#!/usr/bin/python3

import re
import sys
from pathlib import Path

dts, *roots = sys.argv[1:]

classes, enums, members = {}, set(), {}
current = None
for line in open(dts):
  m = re.match(r"\s*export declare class (\w+)(?: extends (\w+))? \{", line)
  if m:
    current = m.group(1)
    classes[current] = m.group(2)
    members[current] = []
    continue
  m = re.match(r"export declare type (\w+) = \{", line)
  if m:
    enums.add(m.group(1))
    current = None
    continue
  m = re.match(r"\s*(?:static )?(\w+)\((.*)", line)
  if current and m:
    members[current].append((m.group(1), set(re.findall(r"\w+", re.sub(r"\w+\??:", "", m.group(2))))))

names = set(classes) | enums

def owner(name):
  base = classes.get(name)
  return base if base and re.fullmatch(re.escape(base) + r"_\d+", name) else name

code = "\n".join(p.read_text() for root in roots for p in Path(root).rglob("*.ts"))
dotted = set(re.findall(r"(?:\.\s*|[\"'])(\w+)", code))

wanted = set()
todo = list(dotted & names)
while todo:
  name = todo.pop()
  if name not in names or name in wanted:
    continue
  wanted.add(name)
  if name in classes:
    todo += [classes[name]] if classes[name] else []
    for member, types in members[name]:
      if member in dotted or member == "constructor" and name in dotted:
        todo += types & names

for symbol in sorted({owner(n) for n in wanted}):
  print("    - symbol: " + symbol)
