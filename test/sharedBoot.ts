import initOpenCascade from "../dist/node.js";

type Settings = NonNullable<Parameters<typeof initOpenCascade>[0]>;

const boots = new Map<string, { settings: Settings; oc: ReturnType<typeof initOpenCascade> }>();

const sameSettings = (a: Settings, b: Settings) =>
  (Object.keys({ ...a, ...b }) as (keyof Settings)[]).every((name) => a[name] === b[name]);

export default function sharedBoot(settings: Settings = {}) {
  const key = settings.mainWasm ?? "";
  const boot = boots.get(key) ?? { settings, oc: initOpenCascade(settings) };
  if (!sameSettings(boot.settings, settings)) throw new Error(`${key || "default wasm"} already booted with different settings`);
  boots.set(key, boot);
  return boot.oc;
}
