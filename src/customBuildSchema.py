from Common import codegenFlags

emccFlags = {
  "required": False,
  "type": "list",
  "schema": {
    "type": "string",
  },
  "default": [
    *codegenFlags,
    "-Wl,-mllvm,-wasm-enable-eh",
    "-sEXPORT_ES6=1",
    "-sEXPORTED_RUNTIME_METHODS=['FS','HEAP8','HEAPU8','getExceptionMessage','getCppExceptionThrownObjectFromWebAssemblyException','decrementExceptionRefcount']",
    "-sINITIAL_MEMORY=100MB",
    "-sMAXIMUM_MEMORY=4GB",
    "-sALLOW_MEMORY_GROWTH=1",
    "-sSTACK_SIZE=5MB",
    "--no-entry",
  ],
}

build = {
  "bindings": {
    "required": False,
    "type": "list",
    "schema": {
      "type": "dict",
      "schema": {
        "symbol": {
          "required": True,
          "type": "string",
        },
      },
    },
    "default": [],
  },
  "emccFlags": emccFlags,
  "name": {
    "required": True,
    "type": "string",
  },
  "additionalBindCode": {
    "required": False,
    "type": "string",
    "default": "",
  },
}

schema = {
  "mainBuild": {
    "required": True,
    "type": "dict",
    "schema": build,
  },
  "extraBuilds": {
    "required": False,
    "type": "list",
    "schema": {
      "type": "dict",
      "schema": build,
    },
    "default": [],
  },
  "additionalCppCode": {
    "required": False,
    "type": "string",
    "default": "",
  },
  "generateTypescriptDefinitions": {
    "required": False,
    "type": "boolean",
    "default": True,
  },
}
