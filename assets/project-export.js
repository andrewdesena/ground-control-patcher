/* SD-ready project archives. Binary patterns stay intact; export never writes to the card. */
(function (root) {
  "use strict";
  const F = root.GCFormat || require("./pattern-format.js");
  const Store = root.GCCardStore || require("./card-store.js");
  const enc = new TextEncoder();
  function projectDefaults() {
    const out = {
      BPM: 120,
      Muted: Array(12).fill("0"),
      QuantizedMute: Array(12).fill("0"),
      modulationTrack: 1,
      modulationSubtrack: 1,
      modulationPolarity: "Unipolar",
      modulationSource: "Velocity",
      modulationSlideMode: "Instant",
      DrumMap: ["C1", "C1#", "D1", "D1#", "E1", "F1", "F1#", "G1"],
    };
    for (let t = 1; t <= 3; t++)
      out["Track" + t + "Scale"] = {
        Scale: 0,
        Root: 0,
        Custom: Array.from({ length: 12 }, (_, i) => i),
      };
    for (let i = 0; i < 4; i++) out["Cv" + i] = { Type: 0, Param: 0 };
    return out;
  }
  function trackDefaults(track) {
    return {
      direction: 0,
      slide: 50,
      shuffle: 50,
      humanize: track === "D" ? Array(9).fill(0) : 0,
      ratchet: track === "D" ? Array(9).fill(0) : 0,
      ArpEngaged: 0,
      ...(track === "D"
        ? { triggerlength: Array(9).fill(50) }
        : { gatelength: 50 }),
      patternChain: ["A"],
    };
  }

  async function files({
    project,
    documents = {},
    settings = {},
    store = null,
  }) {
    if (!/^project[A-Z0-9_-]*$/i.test(project))
      throw new Error("Invalid project folder name");
    const out = new Map();
    const tree = store ? await store.tree() : {};
    const readJSON = async (path) => {
      const bytes = store
        ? await store.optional(path, { remember: false })
        : null;
      return bytes ? F.parseText(new TextDecoder().decode(bytes)) : {};
    };
    const addJSON = (path, value) =>
      out.set(path, enc.encode(JSON.stringify(value) + "\n"));
    const projectPath = project + "/ProjectSettings.txt";
    addJSON(projectPath, {
      ...projectDefaults(),
      ...(await readJSON(projectPath.split("/"))),
      ...settings[projectPath],
    });
    for (const track of ["1", "2", "3", "D"]) {
      const keys = new Set(
        (tree[project]?.[track] || []).map(
          (letter) => project + "/" + track + "/" + letter,
        ),
      );
      for (const key of Object.keys(documents))
        if (key.startsWith(project + "/" + track + "/")) keys.add(key);
      const trackPath = project + "/track" + track + "/TrackSettings.txt";
      const defaults = trackDefaults(track);
      if (keys.size)
        defaults.patternChain = [[...keys].sort()[0].split("/")[2]];
      addJSON(trackPath, {
        ...defaults,
        ...(await readJSON(trackPath.split("/"))),
        ...settings[trackPath],
      });
      for (const key of [...keys].sort()) {
        const path = Store.path(key);
        const bytes = documents[key]
          ? F.encode(documents[key])
          : await store.optional(path, { remember: false });
        if (!bytes)
          throw new Error(
            "A project file disappeared during export: " +
              path.join("/") +
              ". Reopen the card and try again.",
          );
        out.set(path.join("/"), bytes);
      }
    }
    return out;
  }
  // Classic ZIP with stored entries, UTF-8 names, CRC32 and a central directory.
  // No dependency or network service is needed to download a project offline.
  function zip(entries) {
    const chunks = [],
      directory = [];
    let offset = 0;
    if (entries.size > 65535)
      throw new Error("Too many files for a project ZIP");
    for (const [path, data] of entries) {
      if (
        !path ||
        path.includes("\\") ||
        path.split("/").some((part) => !part || part === "." || part === "..")
      )
        throw new Error("Invalid archive path");
      const name = enc.encode(path),
        crc = F.crc32(data);
      if (name.length > 65535 || data.length > 0xffffffff)
        throw new Error("A project file is too large for ZIP");
      const header = new Uint8Array(30 + name.length),
        h = new DataView(header.buffer);
      h.setUint32(0, 0x04034b50, true);
      h.setUint16(4, 20, true);
      h.setUint16(6, 0x800, true);
      h.setUint16(12, 0x21, true); // 1980-01-01, deterministic DOS date.
      h.setUint32(14, crc, true);
      h.setUint32(18, data.length, true);
      h.setUint32(22, data.length, true);
      h.setUint16(26, name.length, true);
      header.set(name, 30);
      const central = new Uint8Array(46 + name.length),
        c = new DataView(central.buffer);
      c.setUint32(0, 0x02014b50, true);
      c.setUint16(4, 20, true);
      c.setUint16(6, 20, true);
      c.setUint16(8, 0x800, true);
      c.setUint16(14, 0x21, true);
      c.setUint32(16, crc, true);
      c.setUint32(20, data.length, true);
      c.setUint32(24, data.length, true);
      c.setUint16(28, name.length, true);
      c.setUint32(42, offset, true);
      central.set(name, 46);
      chunks.push(header, data);
      directory.push(central);
      offset += header.length + data.length;
    }
    const directorySize = directory.reduce((n, bytes) => n + bytes.length, 0);
    if (offset + directorySize + 22 > 0xffffffff)
      throw new Error("Project is too large for ZIP");
    const end = new Uint8Array(22),
      e = new DataView(end.buffer);
    e.setUint32(0, 0x06054b50, true);
    e.setUint16(8, entries.size, true);
    e.setUint16(10, entries.size, true);
    e.setUint32(12, directorySize, true);
    e.setUint32(16, offset, true);
    const out = new Uint8Array(offset + directorySize + end.length);
    let position = 0;
    for (const bytes of [...chunks, ...directory, end]) {
      out.set(bytes, position);
      position += bytes.length;
    }
    return out;
  }
  const api = { projectDefaults, trackDefaults, files, zip };
  if (typeof module !== "undefined") module.exports = api;
  root.GCProjectExport = api;
})(typeof window === "undefined" ? globalThis : window);
