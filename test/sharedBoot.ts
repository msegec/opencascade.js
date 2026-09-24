import initOpenCascade from "../dist/node.js";

type Settings = Parameters<typeof initOpenCascade>[0];

const boots = new Map<string, ReturnType<typeof initOpenCascade>>();

export default function sharedBoot(settings: Settings = {}) {
  const key = settings.mainWasm ?? "";
  const boot = boots.get(key) ?? initOpenCascade(settings);
  boots.set(key, boot);
  return boot;
}
