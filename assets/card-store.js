/* All card operations use exact paths and bytes. No pattern fallback or sidecar I/O. */
(function (root) {
  "use strict";
  const F = root.GCFormat || require("./pattern-format.js");
  const enc = new TextEncoder();
  class CardStore {
    constructor(dir) {
      this.dir = dir;
      this.originals = new Map();
    }
    async handle(parts, create = false) {
      let dir = this.dir;
      for (const part of parts.slice(0, -1))
        dir = await dir.getDirectoryHandle(part, { create });
      return dir.getFileHandle(parts.at(-1), { create });
    }
    async read(parts) {
      const bytes = new Uint8Array(
        await (await (await this.handle(parts)).getFile()).arrayBuffer(),
      );
      this.originals.set(parts.join("/"), bytes.slice());
      return bytes;
    }
    async optional(parts) {
      try {
        return await this.read(parts);
      } catch (e) {
        if (e.name === "NotFoundError") {
          this.originals.set(parts.join("/"), null);
          return null;
        }
        throw e;
      }
    }
    async json(parts, { remember = true } = {}) {
      const key = parts.join("/"),
        known = this.originals.has(key),
        previous = this.originals.get(key);
      const bytes = await this.optional(parts);
      if (!remember && known) this.originals.set(key, previous);
      return bytes ? F.parseText(new TextDecoder().decode(bytes)) : null;
    }
    async rawWrite(parts, bytes) {
      const stream = await (await this.handle(parts, true)).createWritable();
      try {
        await stream.write(bytes);
        await stream.close();
      } catch (e) {
        try {
          await stream.abort();
        } catch {}
        throw e;
      }
      const readback = new Uint8Array(
        await (await (await this.handle(parts)).getFile()).arrayBuffer(),
      );
      if (
        readback.length !== bytes.length ||
        readback.some((b, i) => b !== bytes[i])
      )
        throw new Error("Read-back verification failed: " + parts.join("/"));
    }
    async write(parts, bytes) {
      const key = parts.join("/"),
        hadExpectation = this.originals.has(key),
        expected = this.originals.get(key),
        current = await this.optional(parts);
      if (
        hadExpectation &&
        ((expected === null) !== (current === null) ||
          (expected &&
            current &&
            (current.length !== expected.length ||
              current.some((b, i) => b !== expected[i]))))
      ) {
        this.originals.set(key, expected);
        throw new Error(
          "The card file changed since opening: " +
            key +
            ". Reopen it before saving.",
        );
      }
      if (current)
        await this.rawWrite(
          parts.slice(0, -1).concat(parts.at(-1) + ".bak"),
          current,
        );
      await this.rawWrite(parts, bytes);
      this.originals.set(key, bytes.slice());
    }
    async writeJSON(parts, obj) {
      await this.write(parts, enc.encode(JSON.stringify(obj) + "\n"));
    }
    async deletionSnapshot(plan) {
      const entries = new Map();
      const visit = async (parts, directory) => {
        try {
          if (!directory) {
            const handle = await this.handle(parts);
            entries.set(
              parts.join("/"),
              new Uint8Array(await (await handle.getFile()).arrayBuffer()),
            );
            return;
          }
          let dir = this.dir;
          for (const part of parts) dir = await dir.getDirectoryHandle(part);
          entries.set(parts.join("/"), "directory");
          for await (const entry of dir.values())
            await visit(parts.concat(entry.name), entry.kind === "directory");
        } catch (error) {
          if (error.name !== "NotFoundError") throw error;
          entries.set(parts.join("/"), null);
        }
      };
      for (const target of plan.targets)
        await visit(target.parts, target.directory);
      return entries;
    }
    async prepareDeletion(target, project = false) {
      if (project && !/^project[A-Z0-9_-]*$/i.test(target))
        throw new Error("Invalid card project path");
      const parts = project ? [target] : CardStore.path(target);
      const plan = {
        target,
        project,
        targets: project
          ? [{ parts, directory: true }]
          : [
              { parts, directory: false },
              {
                parts: parts.slice(0, -1).concat(parts.at(-1) + ".bak"),
                directory: false,
              },
            ],
      };
      plan.entries = await this.deletionSnapshot(plan);
      for (const [path, current] of plan.entries) {
        if (!this.originals.has(path) || current === "directory") continue;
        if (!CardStore.sameBytes(this.originals.get(path), current))
          throw new Error(
            "The card file changed since opening: " +
              path +
              ". Reopen the card before deleting.",
          );
      }
      return plan;
    }
    static sameBytes(a, b) {
      return (
        a === b ||
        (a instanceof Uint8Array &&
          b instanceof Uint8Array &&
          a.length === b.length &&
          a.every((v, i) => v === b[i]))
      );
    }
    async deletePlanned(plan) {
      const current = await this.deletionSnapshot(plan);
      if (
        current.size !== plan.entries.size ||
        [...plan.entries].some(
          ([path, bytes]) => !CardStore.sameBytes(bytes, current.get(path)),
        )
      )
        throw new Error(
          "The card changed while confirming deletion. Review it and try again.",
        );
      // Remove a pattern's backup first, so a failed backup deletion preserves its primary file.
      for (const { parts, directory } of [...plan.targets].reverse()) {
        if (plan.entries.get(parts.join("/")) === null) continue;
        let parent = this.dir;
        for (const part of parts.slice(0, -1))
          parent = await parent.getDirectoryHandle(part);
        await parent.removeEntry(parts.at(-1), { recursive: directory });
      }
      const remaining = await this.deletionSnapshot(plan);
      if ([...remaining.values()].some((value) => value !== null))
        throw new Error(
          "Deletion could not be verified. Reopen the card to inspect it.",
        );
      for (const path of plan.entries.keys()) this.originals.delete(path);
    }
    async tree() {
      const projects = {};
      for await (const entry of this.dir.values()) {
        if (
          entry.kind !== "directory" ||
          !/^project[A-Z0-9_-]*$/i.test(entry.name)
        )
          continue;
        projects[entry.name] = {};
        for (const t of ["1", "2", "3", "D"]) {
          const letters = [];
          try {
            const track = await entry.getDirectoryHandle("track" + t);
            for await (const file of track.values()) {
              const m = /^pattern([A-Z])\.txt$/i.exec(file.name);
              if (
                file.kind === "file" &&
                m &&
                F.LETTERS.includes(m[1].toUpperCase())
              )
                letters.push(m[1].toUpperCase());
            }
          } catch (e) {
            if (e.name !== "NotFoundError") throw e;
          }
          projects[entry.name][t] = letters.sort(
            (a, b) => F.LETTERS.indexOf(a) - F.LETTERS.indexOf(b),
          );
        }
      }
      return projects;
    }
    static path(key) {
      const [project, track, letter] = key.split("/");
      if (
        !/^project[A-Z0-9_-]*$/i.test(project) ||
        !["1", "2", "3", "D"].includes(track) ||
        !F.LETTERS.includes(letter)
      )
        throw new Error("Invalid card pattern path");
      return [project, "track" + track, "pattern" + letter + ".txt"];
    }
  }
  if (typeof module !== "undefined") module.exports = CardStore;
  root.GCCardStore = CardStore;
})(typeof window === "undefined" ? globalThis : window);
