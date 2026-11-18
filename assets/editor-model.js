/* One transaction per gesture, with recoverable project/track/letter documents. */
(function (root) {
  "use strict";
  const F = root.GCFormat || require("./pattern-format.js");
  class EditorModel {
    constructor() {
      this.documents = {};
      this.key = "";
      this.undoStack = [];
      this.redoStack = [];
      this.selection = new Set();
      this.cursor = 0;
      this.listeners = new Set();
      this.saved = {};
      this.settings = {};
      this.savedSettings = {};
    }
    get pattern() {
      return this.documents[this.key];
    }
    get dirty() {
      return (
        Object.keys(this.documents).some(
          (k) => JSON.stringify(this.documents[k]) !== this.saved[k],
        ) ||
        Object.keys(this.settings).some(
          (k) => JSON.stringify(this.settings[k]) !== this.savedSettings[k],
        )
      );
    }
    emit() {
      this.listeners.forEach((fn) => fn());
    }
    open(key, pattern) {
      if (!this.documents[key]) {
        this.documents[key] = F.clone(pattern);
        this.saved[key] = JSON.stringify(pattern);
      }
      this.key = key;
      this.selection.clear();
      this.cursor = 0;
      this.emit();
    }
    snapshot() {
      return JSON.stringify({
        documents: this.documents,
        settings: this.settings,
        key: this.key,
      });
    }
    restore(snapshot) {
      const data = JSON.parse(snapshot);
      this.documents = data.documents;
      this.settings = data.settings;
      this.key = data.key || this.key;
    }
    transaction(label, fn) {
      const before = this.snapshot();
      try {
        fn();
        Object.values(this.documents).forEach(F.validate);
      } catch (error) {
        this.restore(before);
        throw error;
      }
      if (before !== this.snapshot()) {
        this.undoStack.push({
          label,
          before,
          after: this.snapshot(),
          key: this.key,
        });
        this.undoStack = this.undoStack.slice(-100);
        this.redoStack = [];
        this.emit();
      }
    }
    commit(label, before) {
      const after = this.snapshot();
      if (before === after) return;
      try {
        Object.values(this.documents).forEach(F.validate);
      } catch (e) {
        this.restore(before);
        this.emit();
        throw e;
      }
      this.undoStack.push({ label, before, after, key: this.key });
      this.undoStack = this.undoStack.slice(-100);
      this.redoStack = [];
      this.emit();
    }
    undo() {
      const item = this.undoStack.pop();
      if (!item) return;
      this.redoStack.push(item);
      this.restore(item.before);
      this.selection.clear();
      this.emit();
    }
    redo() {
      const item = this.redoStack.pop();
      if (!item) return;
      this.undoStack.push(item);
      this.restore(item.after);
      this.selection.clear();
      this.emit();
    }
    notes() {
      return [...this.selection]
        .map((k) => {
          const [s, n] = k.split(":").map(Number),
            pair = this.pattern.steps[s]?.notes.find((p) => p[0] === n);
          return pair ? { s, n, v: pair[1] } : null;
        })
        .filter(Boolean);
    }
    transform(ds, dn, copy = false, source = this.notes()) {
      const p = F.clone(this.pattern);
      if (!copy)
        source.forEach(({ s, n }) => {
          p.steps[s].notes = p.steps[s].notes.filter((pair) => pair[0] !== n);
        });
      const keys = new Set();
      for (const { s, n, v } of source) {
        const step = s + ds,
          pitch = n + dn;
        if (
          step < 0 ||
          step >= p.length ||
          pitch < 0 ||
          pitch > (p.drum ? 7 : 127)
        )
          throw new Error("The whole selection must stay inside the pattern");
        if (p.steps[step].notes.some((pair) => pair[0] === pitch))
          throw new Error("A note already occupies that position");
        if (p.steps[step].notes.length >= 8)
          throw new Error("A step can contain at most eight notes");
        p.steps[step].notes.push([pitch, v]);
        keys.add(step + ":" + pitch);
      }
      this.documents[this.key] = p;
      this.selection = keys;
    }
    deleteSelection() {
      this.transaction("Delete notes", () => {
        this.notes().forEach(({ s, n }) => {
          this.pattern.steps[s].notes = this.pattern.steps[s].notes.filter(
            (pair) => pair[0] !== n,
          );
        });
      });
      this.selection.clear();
    }
    markSaved(key, snapshot) {
      this.saved[key] = snapshot || JSON.stringify(this.documents[key]);
      this.emit();
    }
    export() {
      return {
        format: "gc-editor",
        version: 2,
        documents: F.clone(this.documents),
        active: this.key,
        settings: F.clone(this.settings),
      };
    }
    import(doc) {
      if (
        doc.format !== "gc-editor" ||
        doc.version !== 2 ||
        !doc.documents ||
        !doc.documents[doc.active]
      )
        throw new Error("Choose a Ground Control editor project (version 2)");
      for (const [key, p] of Object.entries(doc.documents)) {
        if (!/^[^/]+\/(1|2|3|D)\/[ABCDEFGHIJKLMNOPQRSTVWYZ]$/.test(key))
          throw new Error("Invalid pattern path in editor project");
        F.validate(p);
      }
      for (const [key, value] of Object.entries(doc.settings || {})) {
        if (
          !/^(?:GlobalSettings\.txt|project[A-Za-z0-9_-]+\/(?:ProjectSettings\.txt|track[123D]\/TrackSettings\.txt))$/.test(
            key,
          ) ||
          !value ||
          typeof value !== "object" ||
          Array.isArray(value)
        )
          throw new Error("Invalid settings path in editor project");
      }
      this.transaction("Import project", () => {
        this.documents = F.clone(doc.documents);
        this.settings = F.clone(doc.settings || {});
        this.key = doc.active;
      });
      this.selection.clear();
      this.emit();
    }
  }
  if (typeof module !== "undefined") module.exports = EditorModel;
  root.GCEditorModel = EditorModel;
})(typeof window === "undefined" ? globalThis : window);
