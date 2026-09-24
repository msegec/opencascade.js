import ocJS from "./opencascade.rockett.js";
import ocWasm from "./opencascade.rockett.wasm";

const initOpenCascade = async ({
  mainJS = ocJS,
  mainWasm = ocWasm,
  worker = undefined,
  libs = [],
  module = {},
} = {}) => {
  const oc = await mainJS({
    locateFile(path) {
      if (path.endsWith('.wasm')) {
        return mainWasm;
      }
      if (path.endsWith('.worker.js') && !!worker) {
        return worker;
      }
      return path;
    },
    ...module
  });
  for (let lib of libs) {
    await oc.loadDynamicLibrary(lib, { loadAsync: true, global: true, nodelete: true, allowUndefined: false });
  }
  return oc;
};

export default initOpenCascade;
