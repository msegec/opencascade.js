import { spawnSync } from "child_process";
import { readFileSync, readdirSync, rmSync } from "fs";
import * as path from "path";
import { fileURLToPath } from "url";

const buildsDir = fileURLToPath(new URL("customBuilds", import.meta.url));
const { version } = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
const runtime = process.env.containerRuntime ?? "podman";
const image = process.env.dockerImageName ?? `localhost/opencascade.js:${version}`;
const user =
  runtime === "podman" ? ["--userns=keep-id"] : ["-u", `${process.getuid?.()}:${process.getgid?.()}`];

export const customBuild = (name: string) => {
  for (const file of readdirSync(buildsDir)) {
    if (file.startsWith(`customBuild.${name}.`)) rmSync(path.join(buildsDir, file));
  }
  const args = ["run", "--rm", "--pull=never", "--network=none", ...user, "--security-opt", "label=disable"];
  const { status, error } = spawnSync(runtime, [...args, "-v", `${buildsDir}:/src`, image, `${name}.yml`], {
    stdio: "inherit",
  });
  if (error || status === null || status >= 125) {
    throw new Error(`${runtime} could not run ${image} for ${name}.yml: ${error?.message ?? `exit ${status}`}`);
  }
  return status;
};

export const requireThreading = (threading: string) => {
  const format = "{{range .Config.Env}}{{println .}}{{end}}";
  const { status, stdout, stderr } = spawnSync(runtime, ["image", "inspect", "--format", format, image], {
    encoding: "utf8",
  });
  if (status !== 0) throw new Error(`${runtime} cannot inspect ${image}: ${stderr.trim()}`);
  const actual = /^threading=(.*)$/m.exec(stdout)?.[1];
  if (actual !== threading) {
    throw new Error(
      `${image} is ${actual ?? "missing threading"}, need ${threading}; set dockerImageName to a ${threading} build image or skipMultiThreaded=1`,
    );
  }
};
