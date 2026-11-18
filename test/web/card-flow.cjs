/* Browser-to-card integration with deterministic File System Access handles. */
const assert = require("node:assert/strict"),
  F = require("../../assets/pattern-format.js");
let pw;
try {
  pw = require("playwright");
} catch {
  pw = require(process.env.PLAYWRIGHT_PATH);
}
(async () => {
  const b = await pw.chromium.launch({ channel: "chrome", headless: true });
  try {
    const page = await b.newPage({ viewport: { width: 1440, height: 1000 } }),
      errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const p = F.blank();
    p.steps[0].notes = [
      [60, 100],
      [64, 80],
      [67, 90],
    ];
    p.steps[2].cc = [[74, 0]];
    p.ccSources[74] = { input: 0, min: 0, max: 127 };
    const original = [...F.encode(p)];
    const files = {
      "projectA/track1/patternE.txt": original,
      "projectA/ProjectSettings.txt": [
        ...new TextEncoder().encode(
          JSON.stringify({ BPM: 123, unknown: "keep me" }),
        ),
      ],
      "projectA/track1/TrackSettings.txt": [
        ...new TextEncoder().encode(
          JSON.stringify({
            gatelength: 60,
            direction: 0,
            shuffle: 50,
            extra: [1, 2, 3],
          }),
        ),
      ],
    };
    await page.addInitScript(
      ({ files }) => {
        class Directory {
          constructor(name) {
            this.name = name;
            this.kind = "directory";
            this.items = new Map();
          }
          async getDirectoryHandle(n, { create = false } = {}) {
            if (!this.items.has(n)) {
              if (!create) throw new DOMException(n, "NotFoundError");
              this.items.set(n, new Directory(n));
            }
            return this.items.get(n);
          }
          async getFileHandle(n, { create = false } = {}) {
            if (!this.items.has(n)) {
              if (!create) throw new DOMException(n, "NotFoundError");
              this.items.set(n, new Handle(n));
            }
            return this.items.get(n);
          }
          async *values() {
            yield* this.items.values();
          }
        }
        class Handle {
          constructor(name) {
            this.name = name;
            this.kind = "file";
            this.data = new Uint8Array();
          }
          async getFile() {
            return new File([this.data], this.name);
          }
          async createWritable() {
            let pending;
            return {
              write: async (data) => {
                if (window.__failWrites) throw new Error("Simulated card full");
                pending =
                  data instanceof Uint8Array
                    ? data
                    : new TextEncoder().encode(data);
              },
              close: async () => {
                this.data = pending.slice();
              },
              abort: async () => {},
            };
          }
        }
        const root = new Directory("GroundControl");
        for (const [path, data] of Object.entries(files)) {
          let dir = root;
          const parts = path.split("/");
          for (const name of parts.slice(0, -1)) {
            if (!dir.items.has(name)) dir.items.set(name, new Directory(name));
            dir = dir.items.get(name);
          }
          const handle = new Handle(parts.at(-1));
          handle.data = Uint8Array.from(data);
          dir.items.set(parts.at(-1), handle);
        }
        window.__card = root;
        window.showDirectoryPicker = async () => root;
        window.__bytes = async (path) => {
          let dir = root;
          const parts = path.split("/");
          for (const name of parts.slice(0, -1)) dir = dir.items.get(name);
          return [...dir.items.get(parts.at(-1)).data];
        };
      },
      { files },
    );
    await page.goto("http://127.0.0.1:8765/#editor");
    const e = page.locator("gc-editor");
    await e.locator("#open").click();
    await page.waitForFunction(
      () =>
        document.querySelector("gc-editor").model.key === "projectA/1/E" &&
        document.querySelector("gc-editor").model.settings[
          "projectA/ProjectSettings.txt"
        ],
    );
    assert.equal(
      await e.evaluate((el) => el.model.pattern.steps[0].notes.length),
      3,
    );
    assert.equal(await e.locator("#bpm").inputValue(), "123");
    await e.evaluate((el) => {
      el.model.selection = new Set(["0:60"]);
      el.selectVisuals();
    });
    await e.locator("#selectedVel").fill("77");
    await e.locator("#selectedVel").dispatchEvent("change");
    await e.locator("#save").click();
    await page.waitForFunction(() => !document.querySelector("gc-editor").busy);
    assert.equal(await e.evaluate((el) => el.model.dirty), false);
    const bytes = await page.evaluate(() =>
        __bytes("projectA/track1/patternE.txt"),
      ),
      backup = await page.evaluate(() =>
        __bytes("projectA/track1/patternE.txt.bak"),
      );
    assert.deepEqual(backup, original);
    const parsed = F.decode(Uint8Array.from(bytes));
    assert.equal(parsed.steps[0].notes.find((n) => n[0] === 60)[1], 77);
    assert.deepEqual(parsed.steps[2].cc, [[74, 0]]);
    assert.deepEqual(parsed.ccSources[74], { input: 0, min: 0, max: 127 });
    // Backups failing must leave the original card data intact and the document dirty.
    await e.evaluate((el) => {
      el.model.selection = new Set(["0:60"]);
      el.selectVisuals();
    });
    await e.locator("#selectedVel").fill("66");
    await e.locator("#selectedVel").dispatchEvent("change");
    await page.evaluate(() => {
      window.__failWrites = true;
    });
    await e.locator("#save").click();
    await page.waitForFunction(() => !document.querySelector("gc-editor").busy);
    assert.equal(await e.evaluate((el) => el.model.dirty), true);
    assert.deepEqual(
      await page.evaluate(() => __bytes("projectA/track1/patternE.txt")),
      bytes,
    );
    // Browser recovery includes the changed document and native settings.
    const draft = await page.evaluate(() =>
      JSON.parse(localStorage.getItem("gc-editor-v2-draft")),
    );
    assert.equal(
      draft.documents["projectA/1/E"].steps[0].notes.find(
        (n) => n[0] === 60,
      )[1],
      66,
    );
    assert.equal(
      draft.settings["projectA/ProjectSettings.txt"].unknown,
      "keep me",
    );
    await page.evaluate(() => {
      window.__failWrites = false;
    });
    await e.locator("#save").click();
    await page.waitForFunction(() => !document.querySelector("gc-editor").busy);
    assert.equal(await e.evaluate((el) => el.model.dirty), false);
    // A new project is undoable and creates a complete native directory structure.
    await e.locator("#newProject").click();
    await e.locator("#projectName").fill("projectB");
    await e
      .locator("#dialog")
      .getByRole("button", { name: "Create", exact: true })
      .click();
    assert.equal(await e.evaluate((el) => el.model.key), "projectB/1/A");
    await e.locator("#undo").click();
    assert.equal(await e.evaluate((el) => el.model.key), "projectA/1/E");
    await e.locator("#redo").click();
    await e.locator("#save").click();
    await page.waitForFunction(() => !document.querySelector("gc-editor").busy);
    assert.equal(await e.evaluate((el) => el.model.dirty), false);
    assert.ok(
      (await page.evaluate(() => __bytes("projectB/trackD/TrackSettings.txt")))
        .length,
    );
    // An imported offline pattern gets missing project/track scaffolding when attached.
    const offline = F.blank();
    offline.steps[0].notes = [[72, 90]];
    await e.locator("#file").setInputFiles({
      name: "offline.json",
      mimeType: "application/json",
      buffer: Buffer.from(
        JSON.stringify({
          format: "gc-editor",
          version: 2,
          documents: { "projectC/1/A": offline },
          active: "projectC/1/A",
        }),
      ),
    });
    await page.waitForFunction(
      () => document.querySelector("gc-editor").model.key === "projectC/1/A",
    );
    await e.locator("#open").click();
    await page.waitForFunction(
      () => !!document.querySelector("gc-editor").store,
    );
    await e.locator("#save").click();
    await page.waitForFunction(() => !document.querySelector("gc-editor").busy);
    assert.equal(await e.evaluate((el) => el.model.dirty), false);
    assert.ok(
      (await page.evaluate(() => __bytes("projectC/ProjectSettings.txt")))
        .length,
    );
    assert.ok(
      (await page.evaluate(() => __bytes("projectC/trackD/patternA.txt")))
        .length,
    );

    // Both release choices build from the same verified stock input; switching invalidates output.
    await page.click("#firmwareTab");
    await page
      .locator("#viewPatcher #file")
      .setInputFiles("testdata/gc326.hex");
    await page.waitForFunction(
      () => !document.getElementById("build").disabled,
    );
    await page.locator("#viewPatcher #build").click();
    await page.waitForFunction(() => !!GCModder.getOutput());
    await page.selectOption("#releaseSelect", "candidate");
    await page.waitForFunction(
      () => !document.getElementById("build").disabled,
    );
    assert.equal(await page.evaluate(() => GCModder.getOutput()), null);
    await page.locator("#viewPatcher #build").click();
    await page.waitForFunction(() => !!GCModder.getOutput());
    assert.equal(
      await page.evaluate(() => GCModder.getOutput().name),
      "GCV326C1.HEX",
    );
    const alphaDownloadEvent = page.waitForEvent("download");
    await page.locator("#viewPatcher #dl").click();
    const alphaDownload = await alphaDownloadEvent;
    assert.equal(alphaDownload.suggestedFilename(), "GCV326C1.HEX");
    assert.equal(
      require("node:fs").readFileSync(await alphaDownload.path(), "utf8"),
      await page.evaluate(() => GCModder.getOutput().text),
    );
    assert.deepEqual(errors, []);
    console.log(
      "PASS browser card read/edit/CC save/backup/failure/recovery and release invalidation",
    );
  } finally {
    await b.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
