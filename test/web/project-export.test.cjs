const { test } = require("node:test");
const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const F = require("../../assets/pattern-format.js");
const Project = require("../../assets/project-export.js");
const encodeJSON = (value) => new TextEncoder().encode(JSON.stringify(value));
function unzip(bytes) {
  const result = spawnSync(
    "python3",
    [
      "-c",
      `import sys,io,zipfile,json,base64
with zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read())) as z:
 assert z.testzip() is None
 print(json.dumps({n:base64.b64encode(z.read(n)).decode() for n in z.namelist()}))`,
    ],
    { input: bytes, encoding: null },
  );
  assert.equal(result.status, 0, result.stderr?.toString());
  return new Map(
    Object.entries(JSON.parse(result.stdout.toString())).map(([name, data]) => [
      name,
      Uint8Array.from(Buffer.from(data, "base64")),
    ]),
  );
}
const json = (bytes) => JSON.parse(new TextDecoder().decode(bytes));
test("offline project ZIP extracts with standard tools and preserves chords, timing, CC and settings", async () => {
  const pattern = F.blank();
  pattern.base.duration = 3;
  pattern.steps[0].notes = [
    [60, 100],
    [64, 80],
  ];
  pattern.steps[2].cc = [[74, 0]];
  pattern.ccSources[74] = { input: 1, min: 127, max: 0 };
  const documents = {
    "projectAway/1/B": pattern,
    "projectOther/1/A": F.blank(),
  };
  const settings = {
    "projectAway/ProjectSettings.txt": { BPM: 134, custom: "preserved" },
    "projectAway/track1/TrackSettings.txt": { gatelength: 81 },
  };
  const before = JSON.stringify({ documents, settings });
  const archive = unzip(
    Project.zip(
      await Project.files({ project: "projectAway", documents, settings }),
    ),
  );
  assert.equal(archive.size, 6);
  assert.ok(
    [...archive.keys()].every((name) => name.startsWith("projectAway/")),
  );
  const loaded = F.decode(archive.get("projectAway/track1/patternB.txt"));
  assert.deepEqual(loaded.steps, pattern.steps);
  assert.deepEqual(loaded.ccSources, pattern.ccSources);
  assert.equal(loaded.base.duration, 3);
  assert.equal(json(archive.get("projectAway/ProjectSettings.txt")).BPM, 134);
  assert.equal(
    json(archive.get("projectAway/ProjectSettings.txt")).custom,
    "preserved",
  );
  assert.equal(
    json(archive.get("projectAway/track1/TrackSettings.txt")).gatelength,
    81,
  );
  assert.equal(
    json(archive.get("projectAway/track1/TrackSettings.txt")).patternChain[0],
    "B",
  );
  assert.ok(
    Array.isArray(
      json(archive.get("projectAway/trackD/TrackSettings.txt")).triggerlength,
    ),
  );
  assert.equal(JSON.stringify({ documents, settings }), before);
});
test("connected project export includes unopened patterns, merges unsaved edits and never writes or resets card baselines", async () => {
  const cardPattern = F.blank();
  cardPattern.steps[0].notes = [[72, 90]];
  const edited = F.clone(cardPattern);
  edited.steps[0].notes = [[76, 70]];
  const original = F.encode(cardPattern);
  const reads = [];
  const source = new Map([
    ["projectA/ProjectSettings.txt", encodeJSON({ BPM: 110, unknown: 42 })],
    [
      "projectA/track1/TrackSettings.txt",
      encodeJSON({ gatelength: 40, unknown: "track" }),
    ],
    ["projectA/track1/patternB.txt", original],
    ["projectA/trackD/patternC.txt", F.encode(F.blank(true))],
  ]);
  const store = {
    tree: async () => ({ projectA: { 1: ["A", "B"], 2: [], 3: [], D: ["C"] } }),
    optional: async (parts, options) => {
      assert.equal(options.remember, false);
      reads.push(parts.join("/"));
      return source.get(parts.join("/")) || null;
    },
  };
  const result = unzip(
    Project.zip(
      await Project.files({
        project: "projectA",
        documents: { "projectA/1/A": edited },
        settings: { "projectA/ProjectSettings.txt": { BPM: 142 } },
        store,
      }),
    ),
  );
  assert.deepEqual(result.get("projectA/track1/patternB.txt"), original);
  assert.deepEqual(
    F.decode(result.get("projectA/track1/patternA.txt")).steps[0].notes,
    [[76, 70]],
  );
  assert.equal(json(result.get("projectA/ProjectSettings.txt")).BPM, 142);
  assert.equal(json(result.get("projectA/ProjectSettings.txt")).unknown, 42);
  assert.equal(
    json(result.get("projectA/track1/TrackSettings.txt")).unknown,
    "track",
  );
  assert.ok(result.has("projectA/trackD/patternC.txt"));
  assert.ok(reads.includes("projectA/track1/patternB.txt"));
});
test("export preserves empty tracks and stops if an unopened card pattern disappears", async () => {
  const entries = await Project.files({ project: "projectEmpty" });
  assert.equal(entries.size, 5);
  assert.ok([...entries.keys()].every((name) => name.endsWith("Settings.txt")));
  await assert.rejects(
    () =>
      Project.files({
        project: "projectA",
        store: {
          tree: async () => ({ projectA: { 1: ["B"] } }),
          optional: async () => null,
        },
      }),
    /disappeared during export/,
  );
  await assert.rejects(
    () => Project.files({ project: "../projectA" }),
    /Invalid project/,
  );
});
test("ZIP handles binary NULs, empty files and UTF-8 names, and rejects traversal", () => {
  const entries = new Map([
    ["projectA/nul.txt", new Uint8Array([0, 255, 1, 0])],
    ["projectA/empty.txt", new Uint8Array()],
    ["projectA/é.txt", new Uint8Array([42])],
  ]);
  assert.deepEqual(unzip(Project.zip(entries)), entries);
  assert.throws(
    () => Project.zip(new Map([["../escape", new Uint8Array()]])),
    /Invalid archive path/,
  );
});
