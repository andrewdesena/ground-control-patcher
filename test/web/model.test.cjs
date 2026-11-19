const { test } = require("node:test");
const assert = require("node:assert/strict");
const F = require("../../assets/pattern-format.js"),
  Model = require("../../assets/editor-model.js"),
  Store = require("../../assets/card-store.js");
test("single-file chords, rests, extreme pitches and zero velocities round-trip safely", () => {
  const p = F.blank();
  p.length = 128;
  p.base.extra = { untouched: true };
  p.steps[0].notes = [
    [0, 1],
    [127, 127],
    [60, 90],
  ];
  p.steps[0].modifier = 3;
  p.steps[0].ratchet = 1;
  p.steps[127].notes = [[72, 81]];
  const bytes = F.encode(p),
    q = F.decode(bytes);
  assert.deepEqual(q.steps, p.steps);
  assert.equal(q.base.extra.untouched, true);
  assert.equal(q.source, "GCP1");
  assert.equal(q.base.steps[0].note, "C-2");
  assert.equal(q.base.steps[1].note, "G8#");
  assert.ok(bytes.length < 12389);
});
test("stock and damaged trailers retain native notes", () => {
  const p = F.blank();
  p.steps[0].notes = [
    [60, 90],
    [64, 70],
  ];
  const bytes = F.encode(p),
    text = bytes.subarray(0, bytes.indexOf(0));
  assert.deepEqual(F.decode(text).steps[0].notes, [[60, 90]]);
  bytes[bytes.length - 1] ^= 1;
  const q = F.decode(bytes);
  assert.deepEqual(q.steps[0].notes, [[60, 90]]);
  assert.equal(q.source, "damaged");
  assert.ok(q.warnings.length);
});
test("CRC uses IEEE representation and preserves explicit CC zero in editor projects", () => {
  assert.equal(F.crc32(new TextEncoder().encode("123456789")), 0xcbf43926);
  const m = new Model();
  m.open("projectA/1/A", F.blank());
  m.transaction("CC", () => m.pattern.steps[0].cc.push([74, 0]));
  const n = new Model();
  n.import(m.export());
  assert.deepEqual(n.pattern.steps[0].cc, [[74, 0]]);
  assert.deepEqual(F.decode(F.encode(n.pattern)).steps[0].cc, [[74, 0]]);
});
test("moves reject overflow and collisions as one transaction, then undo/redo", () => {
  const m = new Model(),
    p = F.blank();
  p.steps[0].notes = [
    [60, 90],
    [64, 100],
  ];
  p.steps[1].notes = [[60, 80]];
  m.open("projectA/1/A", p);
  m.selection = new Set(["0:60", "0:64"]);
  assert.throws(
    () => m.transaction("Move", () => m.transform(1, 0)),
    /already occupies/,
  );
  assert.deepEqual(m.pattern, p);
  m.transaction("Move", () => m.transform(2, 1));
  assert.equal(m.dirty, true);
  assert.deepEqual(m.pattern.steps[2].notes, [
    [61, 90],
    [65, 100],
  ]);
  m.undo();
  assert.equal(m.dirty, false);
  m.redo();
  assert.equal(m.pattern.steps[2].notes.length, 2);
});
test("copy, paste and drum velocity share history and eight-note validation", () => {
  const m = new Model(),
    p = F.blank(true);
  p.steps[0].notes = [[0, 90]];
  m.open("projectA/D/A", p);
  m.selection = new Set(["0:0"]);
  m.transaction("Copy", () => m.transform(1, 0, true));
  assert.equal(m.pattern.steps[0].notes.length, 1);
  assert.equal(m.pattern.steps[1].notes.length, 1);
  assert.throws(
    () => m.transaction("Pitch", () => m.transform(0, 8)),
    /whole selection/,
  );
  m.undo();
  assert.equal(m.pattern.steps[1].notes.length, 0);
});
test("native pattern validation and empty drum serialization", () => {
  const p = F.blank(true),
    bytes = F.encode(p),
    q = F.decode(bytes, true);
  assert.equal(q.base.count, 0);
  assert.equal(q.length, 16);
  const notes = F.blank();
  notes.steps[0].notes = Array.from({ length: 9 }, (_, i) => [i, 100]);
  assert.throws(() => F.encode(notes), /eight/);
  assert.throws(() => Store.path("projectA/1/U"), /Invalid/);
});
class Dir {
  constructor(name = "card") {
    this.name = name;
    this.kind = "directory";
    this.entries = new Map();
  }
  async getDirectoryHandle(n, { create = false } = {}) {
    if (!this.entries.has(n)) {
      if (!create) throw Object.assign(new Error(n), { name: "NotFoundError" });
      this.entries.set(n, new Dir(n));
    }
    return this.entries.get(n);
  }
  async getFileHandle(n, { create = false } = {}) {
    if (!this.entries.has(n)) {
      if (!create) throw Object.assign(new Error(n), { name: "NotFoundError" });
      this.entries.set(n, new File(n));
    }
    return this.entries.get(n);
  }
  async removeEntry(n, { recursive = false } = {}) {
    if (this.failDelete) throw new Error("Simulated permission failure");
    const entry = this.entries.get(n);
    if (!entry) throw Object.assign(new Error(n), { name: "NotFoundError" });
    if (entry.kind === "directory" && entry.entries.size && !recursive)
      throw new Error("Directory is not empty");
    this.entries.delete(n);
  }
  async *values() {
    yield* this.entries.values();
  }
}
class File {
  constructor(name) {
    this.kind = "file";
    this.name = name;
    this.bytes = new Uint8Array();
  }
  async getFile() {
    const bytes = this.bytes.slice();
    return { arrayBuffer: async () => bytes.buffer };
  }
  async createWritable() {
    return {
      write: async (b) => {
        this.bytes = new Uint8Array(b);
      },
      close: async () => {},
      abort: async () => {},
    };
  }
}
test("card writes make exact binary backups, detect external changes, and never create sidecars", async () => {
  const dir = new Dir(),
    store = new Store(dir),
    path = Store.path("projectA/1/A"),
    p = F.blank();
  p.steps[0].notes = [
    [60, 100],
    [64, 70],
  ];
  const first = F.encode(p);
  await store.write(path, first);
  p.steps[0].notes.push([67, 80]);
  await store.write(path, F.encode(p));
  const bak = await store.read(["projectA", "track1", "patternA.txt.bak"]);
  assert.deepEqual(bak, first);
  const file = await store.handle(path);
  file.bytes[0] ^= 1;
  await assert.rejects(() => store.write(path, first), /changed since opening/);
  assert.deepEqual(
    [...(await dir.getDirectoryHandle("projectA")).entries.keys()],
    ["track1"],
  );
  assert.deepEqual(await store.tree(), {
    projectA: { 1: ["A"], 2: [], 3: [], D: [] },
  });
});
test("settings participate in history and recovery without mutating unrelated fields", () => {
  const m = new Model();
  m.open("projectA/1/A", F.blank());
  m.settings["projectA/ProjectSettings.txt"] = { BPM: 120, unknown: "keep,}" };
  m.savedSettings["projectA/ProjectSettings.txt"] = JSON.stringify(
    m.settings["projectA/ProjectSettings.txt"],
  );
  m.transaction("Tempo", () => {
    m.settings["projectA/ProjectSettings.txt"].BPM = 133;
  });
  assert.equal(m.dirty, true);
  m.undo();
  assert.equal(m.dirty, false);
  m.redo();
  assert.equal(
    m.export().settings["projectA/ProjectSettings.txt"].unknown,
    "keep,}",
  );
  assert.equal(F.parseText('{"name":"keep,}"}').name, "keep,}");
});
test("all drum lanes follow editor length and CC capacity is enforced", () => {
  const p = F.blank(true);
  p.length = 32;
  p.base.step_limit = Array(9).fill(16);
  p.steps[31].notes = [[7, 99]];
  const q = F.decode(F.encode(p), true);
  assert.deepEqual(q.base.step_limit.slice(1), Array(8).fill(32));
  assert.deepEqual(q.steps[31].notes, [[7, 99]]);
  const n = F.blank();
  n.steps[0].cc = Array.from({ length: 5 }, (_, i) => [i, 0]);
  assert.throws(() => F.encode(n), /four CC/);
});
test("invalid metadata paths cannot escape the card root", () => {
  const m = new Model();
  assert.throws(
    () =>
      m.import({
        format: "gc-editor",
        version: 2,
        active: "projectA/1/A",
        documents: { "projectA/1/A": F.blank() },
        settings: { "../outside.txt": { a: 1 } },
      }),
    /Invalid settings path/,
  );
});
test("undo creating a pattern restores a valid active document", () => {
  const m = new Model();
  m.open("projectA/1/A", F.blank());
  m.transaction("New pattern", () => {
    m.documents["projectA/1/B"] = F.blank();
    m.key = "projectA/1/B";
  });
  m.undo();
  assert.equal(m.key, "projectA/1/A");
  assert.ok(m.pattern);
  m.redo();
  assert.equal(m.key, "projectA/1/B");
  assert.ok(m.pattern);
});
test("empty CC lanes persist their controller assignment before recording", () => {
  const p = F.blank();
  p.ccLanes = [74, 1];
  const q = F.decode(F.encode(p));
  assert.deepEqual(q.ccLanes, [1, 74]);
  assert.equal(q.base.count, 16);
  assert.equal(q.steps.flatMap((s) => s.cc).length, 0);
});
test("native duration table indices stay within the eight supported rates", () => {
  const p = F.blank();
  p.base.duration = 8;
  assert.throws(() => F.encode(p), /Step duration/);
});
test("a file created externally after a missing-file read is treated as a conflict", async () => {
  const dir = new Dir(),
    store = new Store(dir),
    parts = ["projectA", "track1", "patternA.txt"];
  assert.equal(await store.optional(parts), null);
  await store.rawWrite(parts, new Uint8Array([1, 2]));
  await assert.rejects(
    () => store.write(parts, new Uint8Array([3, 4])),
    /changed since opening/,
  );
  assert.deepEqual(await store.read(parts), new Uint8Array([1, 2]));
});
test("metadata preflight reads do not erase the original conflict baseline", async () => {
  const s = new Store(new Dir()),
    parts = ["projectA", "ProjectSettings.txt"];
  await s.writeJSON(parts, { BPM: 120 });
  await s.json(parts);
  await s.rawWrite(parts, new TextEncoder().encode('{"BPM":140}'));
  assert.equal((await s.json(parts, { remember: false })).BPM, 140);
  await assert.rejects(
    () => s.writeJSON(parts, { BPM: 133 }),
    /changed since opening/,
  );
});

test("pattern deletion removes primary and backup, preserves neighbors, and permits reuse", async () => {
  const root = new Dir(),
    store = new Store(root),
    bytes = F.encode(F.blank());
  await store.write(Store.path("projectA/1/A"), bytes);
  await store.write(Store.path("projectA/1/A"), bytes);
  await store.write(Store.path("projectA/1/B"), bytes);
  const plan = await store.prepareDeletion("projectA/1/A");
  await store.deletePlanned(plan);
  assert.equal(await store.optional(Store.path("projectA/1/A")), null);
  assert.equal(
    await store.optional(["projectA", "track1", "patternA.txt.bak"]),
    null,
  );
  assert.deepEqual(await store.read(Store.path("projectA/1/B")), bytes);
  await store.write(Store.path("projectA/1/A"), bytes);
  assert.deepEqual(await store.read(Store.path("projectA/1/A")), bytes);
});
test("deletion rejects stale contents, confirmation-time changes and unsafe project paths", async () => {
  const root = new Dir(),
    store = new Store(root),
    path = Store.path("projectA/1/A");
  await store.write(path, F.encode(F.blank()));
  (await store.handle(path)).bytes[0] ^= 1;
  await assert.rejects(
    () => store.prepareDeletion("projectA/1/A"),
    /changed since opening/,
  );
  await store.read(path);
  const plan = await store.prepareDeletion("projectA", true);
  await store.rawWrite(["projectA", "new-file.txt"], new Uint8Array([1]));
  await assert.rejects(
    () => store.deletePlanned(plan),
    /changed while confirming/,
  );
  assert.ok(await store.optional(path));
  for (const name of ["..", "projectA/../projectB", "", "GlobalSettings.txt"])
    await assert.rejects(() => store.prepareDeletion(name, true), /Invalid/);
});
test("project deletion removes all contents, and denied deletion preserves the card", async () => {
  const root = new Dir(),
    store = new Store(root),
    bytes = F.encode(F.blank());
  for (const project of ["projectA", "projectB"])
    await store.write(Store.path(project + "/1/A"), bytes);
  await store.rawWrite(["projectA", "other", "extra.txt"], new Uint8Array([2]));
  const plan = await store.prepareDeletion("projectA", true);
  root.failDelete = true;
  await assert.rejects(() => store.deletePlanned(plan), /permission/);
  assert.ok(await store.optional(Store.path("projectA/1/A")));
  root.failDelete = false;
  await store.deletePlanned(plan);
  assert.equal(root.entries.has("projectA"), false);
  assert.deepEqual(await store.read(Store.path("projectB/1/A")), bytes);
});

test("an empty project retains settings through export and recovery after its last pattern is deleted", () => {
  const m = new Model();
  m.settings["projectA/ProjectSettings.txt"] = { BPM: 123 };
  m.key = "";
  const n = new Model();
  n.import(m.export());
  assert.equal(n.key, "");
  assert.deepEqual(n.documents, {});
  assert.deepEqual(n.settings["projectA/ProjectSettings.txt"], { BPM: 123 });
});

test("read-only export reads preserve conflict detection baselines, including missing files", async () => {
  const store = new Store(new Dir()),
    path = Store.path("projectA/1/A");
  const bytes = F.encode(F.blank());
  await store.write(path, bytes);
  const expected = store.originals.get(path.join("/"));
  (await store.handle(path)).bytes[0] ^= 1;
  await store.optional(path, { remember: false });
  assert.deepEqual(store.originals.get(path.join("/")), expected);
  await assert.rejects(() => store.write(path, bytes), /changed since opening/);
  const missing = Store.path("projectA/1/B");
  assert.equal(await store.optional(missing, { remember: false }), null);
  assert.equal(store.originals.has(missing.join("/")), false);
});
