import { readdirSync } from "fs";
import tiers from "./jest.tiers.cjs";

const slow = tiers.projects
  .find((project) => project.displayName === "slow")
  .testMatch.map((path) => path.replace("<rootDir>/", ""));

const fast = readdirSync(new URL(".", import.meta.url))
  .filter((file) => file.endsWith(".test.ts") && !slow.includes(file))
  .sort();

for (const file of fast) await import(`./${file}`);
