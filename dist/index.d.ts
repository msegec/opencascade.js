import type { RockettInstance } from "./rockett-helpers.js";
export * from "./opencascade.rockett.js";
export * from "./rockett-helpers.js";

type OpenCascadeModuleObject = {
  [key: string]: any;
};

export default function initOpenCascade(
  settings?: {
    mainJS?: (module?: OpenCascadeModuleObject) => Promise<any>;
    mainWasm?: string;
    worker?: string;
    libs?: string[];
    module?: OpenCascadeModuleObject;
  },
): Promise<RockettInstance>;
