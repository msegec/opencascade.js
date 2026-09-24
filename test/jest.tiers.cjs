const tier = { rootDir: __dirname, extensionsToTreatAsEsm: [".ts"] };

module.exports = {
  projects: [
    {
      ...tier,
      displayName: "fast",
      testMatch: ["<rootDir>/fast.suite.ts"],
      moduleNameMapper: { "^opencascade\\.js/dist/node(\\.js)?$": "<rootDir>/sharedBoot.ts" },
    },
    {
      ...tier,
      displayName: "slow",
      testMatch: ["customBuilds", "multi-threaded", "progressIndicator", "testBindings"].map(
        (name) => `<rootDir>/${name}.test.ts`,
      ),
    },
  ],
};
