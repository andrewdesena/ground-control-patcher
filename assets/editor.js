/* Ground Control step-native piano roll, with gesture transactions and binary card I/O. */
(function () {
  "use strict";
  const F = window.GCFormat,
    Model = window.GCEditorModel,
    Store = window.GCCardStore,
    Project = window.GCProjectExport;
  const esc = (s) =>
    String(s).replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const projectDefaults = Project.projectDefaults,
    trackDefaults = Project.trackDefaults;
  const DURATIONS = [
    "1/4",
    "1/8",
    "1/16",
    "1/32",
    "1/4 triplet",
    "1/8 triplet",
    "1/16 triplet",
    "1/32 triplet",
  ];
  const CC_NAMES = {
    1: "Mod wheel",
    2: "Breath",
    7: "Volume",
    10: "Pan",
    11: "Expression",
    64: "Sustain",
    71: "Resonance",
    74: "Cutoff",
  };
  const CSS = `
  :host{--bg:#101318;--panel:#191e25;--line:#303844;--muted:#9ba9ba;--fg:#e9eef5;--accent:#74dac1;display:block;background:var(--bg);color:var(--fg);font:13px/1.45 system-ui,sans-serif;min-height:78vh}
  *{box-sizing:border-box}button,input,select{font:inherit;color:inherit}button,select,input[type=number],input[type=text]{border:1px solid var(--line);background:#222a34;border-radius:5px;padding:6px 9px}button{cursor:pointer;white-space:nowrap}button:hover{background:#303c49}button:disabled{opacity:.4;cursor:default}button.active{background:#294b45;border-color:var(--accent);color:var(--accent)}button.primary{background:var(--accent);color:#11251f;border-color:var(--accent);font-weight:650}:focus-visible{outline:2px solid var(--accent);outline-offset:2px}input[type=number]{width:67px}label{display:inline-flex;align-items:center;gap:5px;color:var(--muted);font-size:12px}label input{color:var(--fg)}
  .top{display:flex;align-items:center;flex-wrap:wrap;gap:8px;padding:12px 16px;background:var(--panel);border-bottom:1px solid var(--line)}.brand{font-weight:700;font-size:14px;letter-spacing:.02em;margin-right:12px}.spacer{flex:1}.status{font-size:12px;color:var(--muted)}.lane-toolbar .status{font-size:11px}.lane-tabs,.cc-controls{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.lane-tabs{width:100%}.cc-controls[hidden]{display:none}.dirty{color:#ffd184}.shell{display:grid;grid-template-columns:210px minmax(0,1fr)}aside{background:#141920;border-right:1px solid var(--line);padding:14px 10px;max-height:calc(100vh - 180px);overflow:auto}aside h2{font-size:10px;color:var(--muted);letter-spacing:.13em;margin:0 6px 12px}aside button{width:100%;text-align:left;margin-bottom:4px}details{margin:4px 0}summary{cursor:pointer;color:var(--muted);padding:5px}.pattern{padding-left:22px;font-size:12px}.work{min-width:0;padding:14px 18px 20px}.title{display:flex;align-items:center;gap:10px;margin-bottom:12px}.title strong{font-size:16px}.tree-row{display:flex;gap:4px;align-items:center}.tree-row>button:first-child{flex:1;min-width:0}.tree-delete{width:auto;text-align:center;padding:4px 7px;color:#efa5a5}.tree-project{display:inline-flex;align-items:center;gap:4px;width:calc(100% - 14px);vertical-align:middle}.tree-project>span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis}.tree-project button{margin:0}.tree-add{font-size:11px;color:var(--muted)}[hidden]{display:none!important}.tools{display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin:10px 0}.tools .split{border-left:1px solid var(--line);height:20px;margin:0 3px}.help{color:var(--muted);font-size:11px;margin:9px 0}.warning{padding:10px;border:1px solid #765c2d;background:#30281a;color:#ffe0a2;border-radius:6px;margin-bottom:8px}.warning[hidden]{display:none}
  .viewport{height:48vh;min-height:230px;overflow:auto;border:1px solid var(--line);border-radius:6px;position:relative;overscroll-behavior:contain;background:#11161d;touch-action:none;user-select:none}.sheet{position:relative;min-height:100%}.ruler{height:27px;position:sticky;top:0;z-index:5;background:#222a34;display:flex;margin-left:58px;border-bottom:1px solid #465263}.tick{position:absolute;top:4px;font:10px ui-monospace,monospace;color:var(--muted);padding-left:5px}.ruler .insert{height:27px;background:#74dac130;position:absolute;top:0;border-left:2px solid var(--accent)}.keyboard{position:sticky;left:0;z-index:4;width:58px;background:#252e3a}.key{width:58px;border-bottom:1px solid #45505f;text-align:right;padding-right:7px;font:10px ui-monospace,monospace;display:flex;align-items:center;justify-content:flex-end;cursor:pointer}.key.black{background:#111820;color:#9daabd}.key.c{color:#fff;background:#3b4655}.grid{position:absolute;top:27px;left:58px;right:0;bottom:0;background-image:linear-gradient(to right,#53637466 1px,transparent 1px),linear-gradient(to bottom,#39455577 1px,transparent 1px);cursor:default}.blackrow{position:absolute;left:0;right:0;background:#0003;pointer-events:none}.beatline{position:absolute;top:0;bottom:0;border-left:1px solid #8398b044;pointer-events:none}.note{position:absolute;border:1px solid #a4e8d0a0;border-radius:3px;min-height:8px;background:#5bbca3;color:#0b2720;font:10px ui-monospace,monospace;overflow:hidden;padding-left:4px;cursor:grab;display:flex;align-items:center;user-select:none}.note.selected{outline:2px solid #fff;outline-offset:-2px;color:#fff}.note.ghost{opacity:.5}.marquee{position:absolute;border:1px solid var(--accent);background:#74dac125;pointer-events:none;z-index:7}.playhead{position:absolute;top:27px;bottom:0;border-left:2px solid #fff;z-index:6;pointer-events:none}.loop-region{position:absolute;top:0;height:27px;background:#d6bc7530;border-top:3px solid #d6bc75;pointer-events:none}
  .inspector{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:10px 0;border-bottom:1px solid var(--line)}.inspector span{font-size:12px;color:var(--muted)}.automation{margin-top:10px;min-height:260px;height:auto;resize:vertical;overflow:auto;border:1px solid var(--line);border-radius:6px}.lane-toolbar{display:flex;align-items:center;gap:7px;position:sticky;top:0;background:var(--panel);padding:8px;z-index:3;flex-wrap:wrap}.lane-scroll{overflow-x:auto;overflow-y:hidden}.lane{height:105px;position:relative;margin-left:58px;background:repeating-linear-gradient(to bottom,transparent 0,transparent 25px,#303c4955 25px,#303c4955 26px);cursor:crosshair}.value{position:absolute;bottom:0;min-width:4px;background:#74dac180;border-top:3px solid var(--accent);cursor:ns-resize}.value.selected{background:#74dac1bd;border-color:#fff}.value span{position:absolute;bottom:4px;left:2px;font-size:10px;color:#eafbf6}.lane-info{font-size:11px;color:var(--muted);padding:6px 12px}.settings{margin-top:12px;background:var(--panel);padding:12px;border-radius:6px}.settings[hidden]{display:none}.settings h3{margin:0 0 10px;font-size:12px}.settings .fields{display:flex;gap:12px;flex-wrap:wrap}.toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:100;background:#283b39;border:1px solid var(--accent);padding:10px 18px;border-radius:7px;max-width:90vw;box-shadow:0 8px 30px #0008}.toast[hidden]{display:none}.modal{border:1px solid var(--line);border-radius:10px;background:#1c242e;color:var(--fg);max-width:500px;padding:24px}.modal::backdrop{background:#0009}.modal h2{margin-top:0}.modal .actions{display:flex;gap:8px;justify-content:flex-end;margin-top:20px}.modal p{color:var(--muted)}
  @media(max-width:850px){.shell{grid-template-columns:150px minmax(0,1fr)}.work{padding:12px 10px}.top{padding:10px}.brand{width:100%}aside{padding:10px 6px}}@media(max-width:620px){.shell{grid-template-columns:1fr}aside{max-height:170px;border-bottom:1px solid var(--line)}.viewport{height:48vh}.title{flex-wrap:wrap}.top .status{width:100%}}`;
  const TPL = `
  <div class="top"><span class="brand">GROUND CONTROL <span style="color:var(--muted);font-weight:400">/ PATTERN EDITOR</span></span>
    <button id="play" title="Play / stop (Space)">▶ Play</button><button id="stop" title="Stop and return to start">■ Stop</button>
    <label>BPM <input id="bpm" type="number" min="30" max="300" value="120"></label><button id="loop" class="active">Loop</button>
    <span class="spacer"></span><span id="dirty" class="status" role="status">Saved locally</span><button id="open">Open SD card</button><button id="save" class="primary" disabled>Save changes</button>
  </div>
  <div class="shell"><aside><h2>PROJECTS & PATTERNS</h2><div id="browser"></div><button id="newProject">+ New project</button><button id="import">Import file</button><input id="file" type="file" accept=".txt,.json" hidden><button id="exportFolder" class="primary">Download project ZIP</button><button id="export" title="Workspace backup for reopening in the editor">Export editor project</button><p class="help">ZIP: SD-ready project folder.<br>JSON: editor workspace backup.</p><button id="exportPattern">Export pattern file</button><button id="exportNotes">Export notes only</button><a class="help" href="docs/reference/editor.html" target="_blank" style="display:block;padding:6px;color:var(--accent)">Controls &amp; instructions ↗</a><button id="restore" hidden>Recover browser draft</button></aside>
  <main class="work"><div id="emptyWorkspace" hidden><h2>No pattern selected</h2><p class="help">Choose a pattern in the tree, add a pattern to an empty track, or create a new project.</p></div><div id="patternWork"><div class="title"><strong id="title"></strong><span class="spacer"></span><button id="newPattern">+ Pattern</button><button id="copyPattern">Copy pattern</button><button id="settingsBtn">Settings</button></div>
  <div id="warning" class="warning" role="status" hidden></div>
  <div class="tools"><button id="pointer" class="active" title="Select and move notes">↖ Select</button><button id="draw" title="Draw / erase (B)">✎ Draw</button><span class="split"></span><button id="undo" title="Undo (Cmd/Ctrl Z)">↶ Undo</button><button id="redo" title="Redo (Cmd/Ctrl Shift Z)">↷ Redo</button><button id="duplicate" title="Duplicate selection (Cmd/Ctrl D)">Duplicate</button><button id="delete">Delete</button><span class="split"></span><label>Steps <input id="length" type="number" min="1" max="128"></label><label>Step duration <select id="duration" aria-label="Step duration" title="Duration of every step in this pattern">${DURATIONS.map((name, i) => `<option value="${i}">${name}</option>`).join("")}</select></label><label>New velocity <input id="velocity" type="number" min="1" max="127" value="100"></label><span class="spacer"></span><label>Time zoom <input id="zoomX" type="range" min="18" max="80" value="36" aria-label="Horizontal zoom" style="width:65px"></label><label>Pitch <input id="zoomY" type="range" min="12" max="30" value="20" aria-label="Vertical zoom" style="width:55px"></label><button id="fit">Fit notes</button><button id="fitTime">Fit pattern</button></div>
  <div class="viewport" id="viewport" tabindex="0" aria-label="Piano roll. Double-click to insert. Drag notes to move. B toggles draw mode."><div class="sheet" id="sheet"></div></div>
  <div class="inspector"><span id="selection">No notes selected</span><label>Velocity <input id="selectedVel" type="number" min="1" max="127" disabled></label><button id="tie" title="Tie applies to every note on selected steps">Tie</button><button id="slide">Slide</button><button id="ratchet">Ratchet</button><button id="clear">Clear pattern</button></div>
  <div class="automation"><div class="lane-toolbar"><div id="lane" class="lane-tabs" role="group" aria-label="Automation lanes"></div><label>CC <input id="ccNumber" type="number" min="0" max="127" value="74"></label><button id="addCC">+ Add CC lane</button><span class="status" id="laneCount"></span><div id="ccControls" class="cc-controls" hidden><button id="removeCC">Remove CC lane</button><label>Record on module from <select id="ccSource" aria-label="CC recording source"><option value="0">MIDI / editor</option><option value="1">CV input 1</option><option value="2">CV input 2</option><option value="3">CV input 3</option><option value="4">CV input 4</option></select></label><label>Min <input id="ccMin" type="number" min="0" max="127" value="0" style="width:52px"></label><label>Max <input id="ccMax" type="number" min="0" max="127" value="127" style="width:52px"></label><label>Value <input id="ccValue" type="number" min="0" max="127" value="0" style="width:52px"></label></div></div><div class="lane-info" id="laneStatus" role="status"></div><div class="lane-info" id="laneHelp"></div><div id="laneScroll" class="lane-scroll"><div class="lane" id="laneGraph"></div></div></div>
  <div class="settings" id="settings" hidden><h3>Pattern and track settings</h3><div id="settingsFields" class="fields"></div><p class="help">Tie, slide and ratchet belong to the whole step. Notes use fixed steps; independent note lengths are not stored by the module.</p><p class="help">Preview uses a simple browser instrument with straight step timing. Hardware shuffle, generators, CV outputs and modulation behavior are not simulated.</p></div>
  <div class="help" id="help">Double-click: insert/remove · Drag note: move · Drag empty space: select · Shift-click: add to selection · Option/Alt-drag: copy · B: draw · Space: play</div>
  </div></main></div><div id="toast" class="toast" role="status" hidden></div>
  <dialog id="dialog" class="modal"><h2 id="dialogTitle"></h2><p id="dialogText"></p><div id="dialogFields"></div><div id="dialogActions" class="actions"></div></dialog>`;
  class GCEditor extends HTMLElement {
    connectedCallback() {
      if (this.initialized) return;
      this.initialized = true;
      this.attachShadow({ mode: "open" }).innerHTML =
        "<style>" + CSS + "</style>" + TPL;
      this.$ = (id) => this.shadowRoot.getElementById(id);
      this.model = new Model();
      this.tree = {};
      this.trackSettings = {};
      this.projectSettings = {};
      this.store = null;
      this.mode = "pointer";
      this.cellW = 36;
      this.cellH = 20;
      this.lane = "velocity";
      this.extraLanes = new Set();
      this.clipboard = [];
      this.viewports = {};
      this.playing = false;
      this.looping = true;
      this.loopStart = 0;
      this.loopEnd = null;
      this.busy = false;
      for (const track of ["1", "2", "3", "D"])
        this.model.open("projectA/" + track + "/A", F.blank(track === "D"));
      this.model.key = "projectA/1/A";
      this.model.listeners.add(() => {
        this.render();
        this.recover();
      });
      this.wire();
      this.render();
      this.fitNotes();
      this.$("restore").hidden = !localStorage.getItem("gc-editor-v2-draft");
      this._api = {
        get model() {
          return this.editor.model;
        },
        format: F,
        editor: this,
        loadPattern: (...a) => this.loadPattern(...a),
        saveAll: () => this.saveAll(),
      };
      this.beforeUnload = (ev) => {
        if (this.model.dirty) {
          ev.preventDefault();
          ev.returnValue = "";
        }
      };
      window.addEventListener("beforeunload", this.beforeUnload);
      this.visibility = () => {
        if (document.hidden) this.stop();
      };
      document.addEventListener("visibilitychange", this.visibility);
    }
    disconnectedCallback() {
      this.stop();
      window.removeEventListener("beforeunload", this.beforeUnload);
      document.removeEventListener("visibilitychange", this.visibility);
    }
    get p() {
      return this.model.pattern;
    }
    get parts() {
      return this.model.key.split("/");
    }
    toast(message) {
      this.$("toast").textContent = message;
      this.$("toast").hidden = false;
      clearTimeout(this.toastTimer);
      this.toastTimer = setTimeout(() => {
        this.$("toast").hidden = true;
      }, 4500);
    }
    guard(fn) {
      return async (...args) => {
        try {
          return await fn(...args);
        } catch (error) {
          this.toast(error.message);
          return false;
        }
      };
    }
    recover() {
      try {
        if (this.model.dirty)
          localStorage.setItem(
            "gc-editor-v2-draft",
            JSON.stringify(this.model.export()),
          );
        else localStorage.removeItem("gc-editor-v2-draft");
      } catch {
        this.$("dirty").textContent = "Browser recovery storage unavailable";
      }
    }
    async modal(title, text, actions, fields = "") {
      if (this.$("dialog").open) return null;
      this.$("dialogTitle").textContent = title;
      this.$("dialogText").textContent = text;
      this.$("dialogFields").innerHTML = fields;
      return new Promise((resolve) => {
        const dialog = this.$("dialog"),
          host = this.$("dialogActions");
        host.innerHTML = "";
        const finish = (value) => {
          dialog.close();
          dialog.oncancel = null;
          resolve(value);
        };
        for (const [value, label] of actions) {
          const b = document.createElement("button");
          b.textContent = label;
          if (value === "save" || value === "ok") b.className = "primary";
          b.onclick = () => finish(value);
          host.append(b);
        }
        dialog.oncancel = (ev) => {
          ev.preventDefault();
          finish(null);
        };
        dialog.showModal();
      });
    }
    selectedSteps() {
      const steps = [...new Set(this.model.notes().map((n) => n.s))];
      return steps.length ? steps : [this.model.cursor];
    }
    action(label, fn) {
      if (this.busy) {
        this.toast("Wait for the current save to finish");
        return;
      }
      try {
        this.model.transaction(label, fn);
      } catch (error) {
        this.toast(error.message);
      }
    }
    async connect() {
      if (this.busy) return;
      if (!window.showDirectoryPicker) {
        this.toast(
          "Direct card access needs Chrome or Edge on HTTPS or localhost. You can still import and export files.",
        );
        return;
      }
      const dir =
        window.__gcSD ||
        (await window.showDirectoryPicker({ mode: "readwrite" }));
      const attaching = !this.store && this.model.dirty;
      if (!attaching && !(await this.leave())) return;
      this.stop();
      this.store = new Store(dir);
      this.cardNeedsReopen = false;
      window.__gcSD = dir;
      window.dispatchEvent(
        new CustomEvent("gc-card-connected", { detail: dir }),
      );
      this.tree = await this.store.tree();
      if (attaching) {
        for (const key of Object.keys(this.model.documents)) {
          const bytes = await this.store.optional(Store.path(key));
          if (
            bytes &&
            JSON.stringify(this.model.documents[key]) === this.model.saved[key]
          ) {
            this.model.documents[key] = F.decode(
              bytes,
              key.split("/")[1] === "D",
            );
            this.model.saved[key] = JSON.stringify(this.model.documents[key]);
          } else if (!bytes) delete this.model.saved[key];
        }
        await this.ensureWorkspace();
        this.render();
        this.toast("Card connected. Your editor workspace is ready to save.");
        return;
      }
      this.model.documents = {};
      this.model.saved = {};
      this.model.settings = {};
      this.model.savedSettings = {};
      this.model.undoStack = [];
      this.model.redoStack = [];
      const project = Object.keys(this.tree).sort()[0];
      this.model.key = "";
      if (!project) {
        this.toast("Card opened. Create a project to get started.");
        this.render();
        return;
      }
      const track = ["1", "2", "3", "D"].find(
        (t) => this.tree[project][t].length,
      );
      if (track)
        await this.loadPattern(
          project + "/" + track + "/" + this.tree[project][track][0],
        );
      else {
        this.render();
      }
    }
    async leave() {
      if (this.busy) return false;
      if (!this.model.dirty) return true;
      const result = await this.modal(
        "Unsaved changes",
        "Save changes before replacing the current workspace?",
        [
          ["cancel", "Cancel"],
          ["discard", "Discard"],
          ["save", "Save"],
        ],
      );
      if (result === "save") return await this.saveAll();
      if (result !== "discard") return false;
      this.model = this.resetModel();
      return true;
    }
    resetModel() {
      const model = new Model();
      model.listeners.add(() => {
        this.render();
        this.recover();
      });
      model.open("projectA/1/A", F.blank());
      return model;
    }
    async loadPattern(key) {
      if (this.gesture) return;
      this.stop();
      this.saveViewport();
      if (!this.model.documents[key]) {
        const pattern = F.decode(
          await this.store.read(Store.path(key)),
          key.split("/")[1] === "D",
        );
        this.model.open(key, pattern);
      } else this.model.open(key, this.model.documents[key]);
      const [project, track] = key.split("/");
      for (const path of [
        [project, "ProjectSettings.txt"],
        [project, "track" + track, "TrackSettings.txt"],
      ]) {
        const k = path.join("/");
        if (!this.model.settings[k]) {
          const value = (await this.store.json(path)) || {};
          this.model.settings[k] = value;
          this.model.savedSettings[k] = JSON.stringify(value);
        }
      }
      this.$("bpm").value =
        this.model.settings[project + "/ProjectSettings.txt"]?.BPM || 120;
      this.extraLanes.clear();
      this.lane = "velocity";
      this.render();
      this.restoreViewport();
    }
    async ensureWorkspace() {
      const projects = [
        ...new Set(
          Object.keys(this.model.documents).map((k) => k.split("/")[0]),
        ),
      ];
      for (const project of projects) {
        const path = [project, "ProjectSettings.txt"],
          key = path.join("/"),
          existing = await this.store.json(path, { remember: false });
        if (!this.model.settings[key]) {
          this.model.settings[key] = existing || projectDefaults();
          if (existing)
            this.model.savedSettings[key] = JSON.stringify(existing);
        }
        if (existing)
          this.model.settings[key] = {
            ...existing,
            ...this.model.settings[key],
          };
        if (!existing) {
          this.model.settings[key] = {
            ...projectDefaults(),
            ...this.model.settings[key],
          };
          delete this.model.savedSettings[key];
        }
        for (const track of ["1", "2", "3", "D"]) {
          const settingsPath = [project, "track" + track, "TrackSettings.txt"],
            settingsKey = settingsPath.join("/"),
            trackExists = await this.store.json(settingsPath, {
              remember: false,
            });
          if (!this.model.settings[settingsKey]) {
            this.model.settings[settingsKey] =
              trackExists || trackDefaults(track);
            if (trackExists)
              this.model.savedSettings[settingsKey] =
                JSON.stringify(trackExists);
          }
          if (trackExists)
            this.model.settings[settingsKey] = {
              ...trackExists,
              ...this.model.settings[settingsKey],
            };
          if (!trackExists) {
            this.model.settings[settingsKey] = {
              ...trackDefaults(track),
              ...this.model.settings[settingsKey],
            };
            delete this.model.savedSettings[settingsKey];
          }
          if (!existing) {
            const patternKey = project + "/" + track + "/A";
            if (!this.model.documents[patternKey]) {
              const bytes = await this.store.optional(Store.path(patternKey));
              this.model.documents[patternKey] = bytes
                ? F.decode(bytes, track === "D")
                : F.blank(track === "D");
              if (bytes)
                this.model.saved[patternKey] = JSON.stringify(
                  this.model.documents[patternKey],
                );
            }
          }
        }
      }
    }
    async saveAll() {
      if (this.busy) return false;
      if (this.cardNeedsReopen) {
        this.toast(
          "Reopen the SD card before saving after an unverified deletion.",
        );
        return false;
      }
      if (!this.store) {
        this.toast("Open an SD card to save, or export an editor project.");
        return false;
      }
      this.busy = true;
      this.inert = true;
      this.stop();
      this.render();
      try {
        await this.ensureWorkspace();
        const pending = Object.entries(this.model.documents).filter(
          ([k, p]) => JSON.stringify(p) !== this.model.saved[k],
        );
        const writes = pending.map(([k, p]) => [
            k,
            F.encode(p),
            JSON.stringify(p),
          ]),
          settings = Object.entries(this.model.settings)
            .filter(
              ([k, v]) => JSON.stringify(v) !== this.model.savedSettings[k],
            )
            .map(([k, v]) => [k, F.clone(v)]);
        for (const [key, bytes, version] of writes) {
          await this.store.write(Store.path(key), bytes);
          this.model.markSaved(key, version);
        }
        for (const [key, value] of settings) {
          await this.store.writeJSON(key.split("/"), value);
          this.model.savedSettings[key] = JSON.stringify(value);
        }
        this.tree = await this.store.tree();
        this.toast(
          "Saved and verified " +
            writes.length +
            " pattern(s). Previous files kept as .bak.",
        );
        return true;
      } catch (error) {
        this.toast(
          "Save stopped: " +
            error.message +
            ". Remaining changes are still in the editor.",
        );
        return false;
      } finally {
        this.busy = false;
        this.inert = false;
        this.render();
        this.recover();
      }
    }
    async newProject() {
      const choice = await this.modal(
        "New project",
        "Create an empty project in the editor. Nothing is written until you save.",
        [
          ["cancel", "Cancel"],
          ["ok", "Create"],
        ],
        '<label>Name <input id="projectName" type="text" value="projectB" maxlength="40"></label>',
      );
      if (choice !== "ok") return;
      const project = this.shadowRoot
        .getElementById("projectName")
        .value.trim();
      if (!/^project[A-Z0-9_-]+$/i.test(project))
        throw new Error(
          "Use project followed by letters, numbers, hyphens or underscores",
        );
      if (
        this.tree[project] ||
        Object.keys(this.model.settings).some((k) =>
          k.startsWith(project + "/"),
        ) ||
        Object.keys(this.model.documents).some((k) =>
          k.startsWith(project + "/"),
        )
      )
        throw new Error("That project already exists");
      this.action("New project", () => {
        for (const track of ["1", "2", "3", "D"]) {
          this.model.documents[project + "/" + track + "/A"] = F.blank(
            track === "D",
          );
          this.model.settings[
            project + "/track" + track + "/TrackSettings.txt"
          ] = trackDefaults(track);
        }
        this.model.settings[project + "/ProjectSettings.txt"] =
          projectDefaults();
        this.model.key = project + "/1/A";
        this.model.selection.clear();
      });
      this.render();
      this.fitNotes();
    }
    async newPattern(copy = false, destination = this.parts) {
      const [project, track] = destination;
      const used = new Set([
        ...(this.tree[project]?.[track] || []),
        ...Object.keys(this.model.documents)
          .filter((k) => k.startsWith(project + "/" + track + "/"))
          .map((k) => k.split("/")[2]),
      ]);
      const available = F.LETTERS.filter((l) => !used.has(l));
      if (!available.length) throw new Error("All 24 pattern letters are used");
      const choice = await this.modal(
        copy ? "Copy pattern" : "New pattern",
        "Choose a destination letter on this track. Existing patterns are preserved.",
        [
          ["cancel", "Cancel"],
          ["ok", copy ? "Copy" : "Create"],
        ],
        '<label>Letter <select id="destLetter">' +
          available.map((l) => "<option>" + l + "</option>").join("") +
          "</select></label>",
      );
      if (choice !== "ok") return;
      const key =
        project +
        "/" +
        track +
        "/" +
        this.shadowRoot.getElementById("destLetter").value;
      this.stop();
      this.action(copy ? "Copy pattern" : "New pattern", () => {
        this.model.documents[key] = copy
          ? F.clone(this.p)
          : F.blank(track === "D");
        this.model.key = key;
        this.model.selection.clear();
      });
      if (this.store) await this.loadPattern(key);
      else this.fitNotes();
    }
    exportableProjects() {
      return [
        ...new Set([
          ...Object.keys(this.tree),
          ...Object.keys(this.model.documents).map((key) => key.split("/")[0]),
          ...Object.keys(this.model.settings).map((key) => key.split("/")[0]),
        ]),
      ]
        .filter((name) => /^project[A-Z0-9_-]*$/i.test(name))
        .sort();
    }
    async exportProjectFolder() {
      if (this.busy) return;
      const projects = this.exportableProjects();
      if (!projects.length) throw new Error("Create or import a project first");
      if (
        (await this.modal(
          "Download project folder",
          "Download a ZIP containing the selected project's current patterns and track/project settings. Unsaved edits are included. Extract it on your computer, then copy the project folder to the SD card root using your file manager. This does not save to the card or mark edits as saved.",
          [
            ["cancel", "Cancel"],
            ["ok", "Download ZIP"],
          ],
          '<label>Project <select id="exportProject">' +
            projects
              .map(
                (name) =>
                  "<option" +
                  (name === this.parts[0] ? " selected" : "") +
                  ">" +
                  esc(name) +
                  "</option>",
              )
              .join("") +
            "</select></label>",
        )) !== "ok"
      )
        return;
      const project = this.$("exportProject").value;
      this.busy = true;
      this.inert = true;
      this.stop();
      this.render();
      try {
        const entries = await Project.files({
          project,
          documents: this.model.documents,
          settings: this.model.settings,
          store: this.store,
        });
        this.download(
          project + ".zip",
          Project.zip(entries),
          "application/zip",
        );
        this.toast(
          "Downloaded " +
            project +
            ".zip. Extract it and copy the " +
            project +
            " folder to the card root. Back up any same-named folder first.",
        );
      } finally {
        this.busy = false;
        this.inert = false;
        this.render();
      }
    }
    download(name, bytes, type) {
      const url = URL.createObjectURL(new Blob([bytes], { type })),
        a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    async importFile(file) {
      if (!file) return;
      if (/\.json$/i.test(file.name)) {
        let doc = JSON.parse(await file.text());
        if (!doc.format && Array.isArray(doc.tracks))
          doc = this.convertLegacy(doc);
        const check = new Model();
        check.import(doc);
        if (!(await this.leave())) return;
        this.model.import(doc);
        this.store = null;
        this.tree = {};
        this.render();
        this.toast(
          "Imported editor project. Open the target SD card when ready to save.",
        );
      } else {
        const pattern = F.decode(
          await file.arrayBuffer(),
          this.p?.drum || false,
        );
        this.action("Import pattern", () => {
          if (!this.model.key)
            this.model.key =
              (Object.keys(this.tree).sort()[0] || "projectA") + "/1/A";
          this.model.documents[this.model.key] = pattern;
          this.model.selection.clear();
        });
        this.fitNotes();
      }
    }
    convertLegacy(doc) {
      const documents = {},
        settings = {
          "projectA/ProjectSettings.txt": { BPM: doc.global?.BPM || 120 },
        };
      for (const tr of doc.tracks || []) {
        if (![1, 2, 3].includes(+tr.index)) continue;
        const p = F.blank();
        p.length = Math.max(
          1,
          Math.min(128, tr.step_limit || doc.step_limit || doc.steps || 32),
        );
        const source =
          tr.steps2 ||
          (tr.steps || []).map((s) => ({
            notes:
              s.note && s.velocity > 0
                ? [[F.noteToMidi(s.note), s.velocity]]
                : [],
            cc: [],
            modifier: s.modifier,
            ratchet: s.ratchet,
          }));
        source.slice(0, 128).forEach((s, i) => {
          p.steps[i] = {
            notes: F.clone(s.notes || []),
            cc: F.clone(s.cc || []),
            modifier: s.modifier || 0,
            ratchet: s.ratchet || 0,
          };
        });
        documents["projectA/" + tr.index + "/A"] = p;
        settings["projectA/track" + tr.index + "/TrackSettings.txt"] = F.clone(
          tr.settings || {},
        );
      }
      if (doc.drum?.steps) {
        const p = F.blank(true);
        p.length = Math.max(1, Math.min(128, doc.steps || 32));
        for (const s of doc.drum.steps)
          if (s.index >= 0 && s.index < 128)
            p.steps[s.index].notes = (s.triggers || []).map((t) => [
              t.pad - 1,
              t.velocity,
            ]);
        documents["projectA/D/A"] = p;
      }
      if (!Object.keys(documents).length)
        throw new Error("This JSON contains no supported tracks");
      return {
        format: "gc-editor",
        version: 2,
        documents,
        settings,
        active: Object.keys(documents)[0],
      };
    }
    renderBrowser() {
      const projects = F.clone(this.tree);
      for (const key of Object.keys(this.model.documents)) {
        const [p, t, l] = key.split("/");
        projects[p] ||= {};
        projects[p][t] ||= [];
        if (!projects[p][t].includes(l)) projects[p][t].push(l);
      }
      for (const key of Object.keys(this.model.settings)) {
        const project = key.split("/")[0];
        if (/^project[A-Z0-9_-]*$/i.test(project)) projects[project] ||= {};
      }
      const [current, track] = this.parts,
        host = this.$("browser");
      const expanded = new Set(
        [...host.querySelectorAll("details[open][data-tree]")].map(
          (node) => node.dataset.tree,
        ),
      );
      host.innerHTML = Object.keys(projects)
        .sort()
        .map(
          (project) =>
            '<details data-tree="' +
            esc(project) +
            '" ' +
            (project === current || expanded.has(project) ? "open" : "") +
            '><summary><span class="tree-project"><span>' +
            esc(project) +
            '</span><button class="tree-delete" data-delete-project="' +
            esc(project) +
            '" aria-label="Delete project ' +
            esc(project) +
            '" title="Delete project">×</button></span></summary>' +
            ["1", "2", "3", "D"]
              .map(
                (t) =>
                  '<details data-tree="' +
                  esc(project + "/" + t) +
                  '" ' +
                  ((project === current && track === t) ||
                  expanded.has(project + "/" + t)
                    ? "open"
                    : "") +
                  "><summary>" +
                  (t === "D" ? "Drums" : "Track " + t) +
                  "</summary>" +
                  (projects[project][t] || [])
                    .sort((a, b) => F.LETTERS.indexOf(a) - F.LETTERS.indexOf(b))
                    .map((l) => {
                      const key = project + "/" + t + "/" + l;
                      const dirty =
                        this.model.documents[key] &&
                        JSON.stringify(this.model.documents[key]) !==
                          this.model.saved[key];
                      return (
                        '<div class="tree-row"><button class="pattern ' +
                        (key === this.model.key ? "active" : "") +
                        '" data-key="' +
                        esc(key) +
                        '">Pattern ' +
                        l +
                        (dirty ? " •" : "") +
                        '</button><button class="tree-delete" data-delete-pattern="' +
                        esc(key) +
                        '" aria-label="Delete pattern ' +
                        esc(key) +
                        '" title="Delete pattern">×</button></div>'
                      );
                    })
                    .join("") +
                  '<button class="tree-add" data-new-pattern="' +
                  esc(project + "/" + t) +
                  '">+ Add pattern</button></details>',
              )
              .join("") +
            "</details>",
        )
        .join("");
      host.querySelectorAll("[data-key]").forEach((b) => {
        b.onclick = this.guard(() => this.switchPattern(b.dataset.key));
      });
      host.querySelectorAll("[data-new-pattern]").forEach((b) => {
        b.onclick = this.guard(() =>
          this.newPattern(false, b.dataset.newPattern.split("/")),
        );
      });
      for (const kind of ["project", "pattern"])
        host.querySelectorAll("[data-delete-" + kind + "]").forEach((b) => {
          b.onclick = this.guard((ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            return this.deleteItem(
              kind === "project"
                ? b.dataset.deleteProject
                : b.dataset.deletePattern,
              kind === "project",
            );
          });
        });
    }
    forgetDeleted(matches, removeSettings) {
      for (const key of Object.keys(this.model.documents))
        if (matches(key)) {
          delete this.model.documents[key];
          delete this.model.saved[key];
          delete this.viewports[key];
        }
      for (const key of Object.keys(this.model.settings))
        if (removeSettings(key)) {
          delete this.model.settings[key];
          delete this.model.savedSettings[key];
        }
      // Saved snapshots and recovery must never recreate a deleted item through Undo.
      this.model.undoStack = [];
      this.model.redoStack = [];
      this.model.selection.clear();
      this.model.cursor = 0;
      this.clipboard = [];
      this.ccSelection = new Set();
      this.lane = "velocity";
      this.extraLanes.clear();
      if (!this.model.documents[this.model.key]) this.model.key = "";
    }
    async selectRemaining() {
      if (this.p) return;
      const keys = new Set(Object.keys(this.model.documents));
      for (const [project, tracks] of Object.entries(this.tree))
        for (const [track, letters] of Object.entries(tracks))
          for (const letter of letters)
            keys.add(project + "/" + track + "/" + letter);
      const key = [...keys].sort()[0];
      if (key) await this.switchPattern(key);
    }
    async deleteItem(target, project = false) {
      if (this.busy || this.cardNeedsReopen) return;
      if (this.gesture || this.laneGesture)
        throw new Error("Finish the current edit before deleting");
      this.stop();
      const plan = this.store
        ? await this.store.prepareDeletion(target, project)
        : null;
      if (this.busy) return;
      const count = plan
        ? [...plan.entries.values()].filter((v) => v instanceof Uint8Array)
            .length
        : 0;
      const description = project
        ? "the whole project folder, including all patterns, settings, backups and any other files inside it"
        : "this pattern file and its .bak backup";
      const result = await this.modal(
        "Delete " + (project ? "project " : "pattern ") + target,
        (this.store
          ? "Permanently remove " +
            description +
            " from the connected SD card (" +
            count +
            " files). "
          : "Remove this " +
            (project ? "project" : "pattern") +
            " from the editor workspace. ") +
          "Unsaved edits in this item will be discarded. Other items stay intact. Deletion cannot be undone and clears edit history. Export a backup first if needed.",
        [
          ["cancel", "Cancel"],
          ["delete", this.store ? "Delete from SD card" : "Delete from editor"],
        ],
      );
      if (result !== "delete") return;
      this.busy = true;
      this.inert = true;
      this.render();
      let failure;
      try {
        if (plan) await this.store.deletePlanned(plan);
        this.forgetDeleted(
          (key) => (project ? key.startsWith(target + "/") : key === target),
          (key) => project && key.startsWith(target + "/"),
        );
        if (this.store) this.tree = await this.store.tree();
      } catch (error) {
        failure = error;
        if (plan) {
          try {
            this.tree = await this.store.tree();
            const after = await this.store.deletionSnapshot(plan);
            const removed = new Set(
              [...plan.entries]
                .filter(
                  ([key, value]) =>
                    value !== null &&
                    (!after.has(key) || after.get(key) === null),
                )
                .map(([key]) => key),
            );
            for (const path of removed) this.store.originals.delete(path);
            if (removed.size) {
              const all = project && after.get(target) === null;
              this.forgetDeleted(
                (key) =>
                  all
                    ? key.startsWith(target + "/")
                    : removed.has(Store.path(key).join("/")),
                (key) =>
                  all ? key.startsWith(target + "/") : removed.has(key),
              );
            }
          } catch {
            this.cardNeedsReopen = true;
          }
        }
      } finally {
        this.busy = false;
        this.inert = false;
        if (!this.cardNeedsReopen) {
          try {
            await this.selectRemaining();
          } catch (error) {
            failure ||= error;
            this.cardNeedsReopen = true;
          }
        }
        this.render();
        this.recover();
        this.$("restore").hidden = !localStorage.getItem("gc-editor-v2-draft");
      }
      this.toast(
        failure
          ? "Deletion stopped: " +
              failure.message +
              (this.cardNeedsReopen
                ? " Reopen the SD card before saving."
                : " Inspect the card before retrying.")
          : "Deleted " +
              target +
              (plan ? " from the SD card and editor." : " from the editor."),
      );
    }
    async switchPattern(key) {
      if (this.busy) return;
      if (this.store) await this.loadPattern(key);
      else {
        this.stop();
        this.saveViewport();
        this.model.open(key, this.model.documents[key]);
        this.restoreViewport();
      }
    }
    render() {
      const empty = !this.p;
      this.$("patternWork").hidden = empty;
      this.$("emptyWorkspace").hidden = !empty;
      for (const id of [
        "play",
        "stop",
        "bpm",
        "loop",
        "export",
        "exportPattern",
        "exportNotes",
      ])
        this.$(id).disabled = empty || this.busy;
      this.$("exportFolder").disabled =
        this.busy || !this.exportableProjects().length;
      this.$("export").disabled =
        this.busy ||
        (!Object.keys(this.model.documents).length &&
          !Object.keys(this.model.settings).length);
      if (empty) {
        this.$("save").disabled =
          !this.store || this.busy || this.cardNeedsReopen || !this.model.dirty;
        this.$("dirty").textContent = this.model.dirty
          ? "● Unsaved settings"
          : "No pattern selected";
        this.$("dirty").classList.toggle("dirty", this.model.dirty);
        this.renderBrowser();
        return;
      }
      const [project, track, letter] = this.parts;
      this.$("title").textContent =
        project + " / Track " + track + " / Pattern " + letter;
      const settingsDirty = Object.keys(this.model.settings).some(
        (k) =>
          JSON.stringify(this.model.settings[k]) !==
          this.model.savedSettings[k],
      );
      this.$("dirty").textContent =
        this.model.dirty || settingsDirty
          ? "● Unsaved changes"
          : "All changes saved";
      this.$("dirty").classList.toggle(
        "dirty",
        this.model.dirty || settingsDirty,
      );
      this.$("save").disabled =
        !this.store ||
        this.busy ||
        this.cardNeedsReopen ||
        (!this.model.dirty && !settingsDirty);
      this.$("open").disabled = this.busy;
      this.$("length").value = this.p.length;
      this.$("duration").value = this.p.base.duration ?? 2;
      this.$("bpm").value =
        this.model.settings[project + "/ProjectSettings.txt"]?.BPM || 120;
      this.$("undo").disabled = !this.model.undoStack.length;
      this.$("redo").disabled = !this.model.redoStack.length;
      this.$("pointer").classList.toggle("active", this.mode === "pointer");
      this.$("draw").classList.toggle("active", this.mode === "draw");
      const ccPresent =
          this.p.steps.some((s) => s.cc.length) ||
          Object.keys(this.p.ccSources || {}).length ||
          this.p.ccLanes?.length,
        warnings = this.p.warnings.slice();
      if (ccPresent)
        warnings.push(
          "CC automation requires the experimental v0.10.0-alpha.1 firmware. v0.9.0 reads chords but does not play these controller lanes.",
        );
      this.$("warning").hidden = !warnings.length;
      this.$("warning").textContent = warnings.join(" ");
      this.renderBrowser();
      this.renderRoll();
      this.renderInspector();
      this.renderLanes();
      this.renderSettings();
    }
    renderRoll() {
      const scroll = this.$("viewport"),
        top = scroll.scrollTop,
        left = scroll.scrollLeft,
        count = this.p.drum ? 8 : 128,
        width = this.p.length * this.cellW,
        height = count * this.cellH;
      let keys = "",
        rows = "",
        beats = "",
        notes = "",
        ticks = "";
      for (let i = 0; i < count; i++) {
        const pitch = count - 1 - i,
          black = !this.p.drum && [1, 3, 6, 8, 10].includes(pitch % 12);
        keys +=
          '<div class="key ' +
          (black ? "black" : pitch % 12 === 0 ? "c" : "") +
          '" data-pitch="' +
          pitch +
          '" style="height:' +
          this.cellH +
          'px">' +
          (this.p.drum ? "Pad " + (pitch + 1) : F.displayNote(pitch)) +
          "</div>";
        if (black)
          rows +=
            '<div class="blackrow" style="top:' +
            i * this.cellH +
            "px;height:" +
            this.cellH +
            'px"></div>';
      }
      for (let s = 0; s < this.p.length; s++) {
        if (!(s % 4)) {
          beats +=
            '<div class="beatline" style="left:' +
            s * this.cellW +
            "px;" +
            (!(s % 16) ? "border-color:#9eb1c299" : "") +
            '"></div>';
          ticks +=
            '<span class="tick" style="left:' +
            s * this.cellW +
            'px">' +
            (s + 1) +
            "</span>";
        }
        for (const [n, v] of this.p.steps[s].notes) {
          const key = s + ":" + n,
            selected = this.model.selection.has(key),
            f = this.p.steps[s];
          notes +=
            '<div class="note ' +
            (selected ? "selected" : "") +
            '" data-note="' +
            key +
            '" style="left:' +
            (s * this.cellW + 1) +
            "px;top:" +
            ((count - 1 - n) * this.cellH + 1) +
            "px;width:" +
            (this.cellW - 2) +
            "px;height:" +
            (this.cellH - 2) +
            "px;background:hsl(" +
            (this.p.drum ? 35 : 162) +
            ",42%," +
            (29 + v * 0.23) +
            '%)" title="' +
            (this.p.drum ? "Pad " + (n + 1) : F.displayNote(n)) +
            " · velocity " +
            v +
            " · step " +
            (s + 1) +
            '">' +
            (this.cellW >= 30
              ? f.modifier & 1
                ? "↗"
                : f.ratchet
                  ? "≋"
                  : v
              : "") +
            "</div>";
        }
      }
      this.$("sheet").style.cssText =
        "width:" + (58 + width) + "px;height:" + (27 + height) + "px";
      this.$("sheet").innerHTML =
        '<div class="ruler" style="width:' +
        width +
        'px">' +
        ticks +
        '<div class="insert" style="left:' +
        this.model.cursor * this.cellW +
        "px;width:" +
        this.cellW +
        'px"></div><div class="loop-region" style="left:' +
        this.loopStart * this.cellW +
        "px;width:" +
        ((this.loopEnd || this.p.length) - this.loopStart) * this.cellW +
        'px"></div></div><div class="keyboard">' +
        keys +
        '</div><div class="grid" style="width:' +
        width +
        "px;height:" +
        height +
        "px;background-size:" +
        this.cellW +
        "px " +
        this.cellH +
        'px">' +
        rows +
        beats +
        notes +
        '</div><div class="playhead" hidden></div>';
      scroll.scrollTop = top;
      scroll.scrollLeft = left;
    }
    renderInspector() {
      const notes = this.model.notes(),
        values = new Set(notes.map((n) => n.v)),
        selected = this.$("selectedVel");
      this.$("selection").textContent = notes.length
        ? notes.length +
          " note(s) · " +
          this.selectedSteps().length +
          " step(s)"
        : "Step " + (this.model.cursor + 1) + " · no notes selected";
      selected.disabled = !notes.length;
      selected.value = values.size === 1 ? notes[0].v : "";
      selected.placeholder = values.size > 1 ? "Mixed" : "";
      for (const [id, mask] of [
        ["tie", 1],
        ["slide", 2],
        ["ratchet", 0],
      ]) {
        const states = this.selectedSteps().map((s) =>
          id === "ratchet"
            ? !!this.p.steps[s].ratchet
            : !!(this.p.steps[s].modifier & mask),
        );
        this.$(id).disabled = this.p.drum;
        this.$(id).classList.toggle("active", states.every(Boolean));
        this.$(id).textContent =
          id[0].toUpperCase() +
          id.slice(1) +
          (states.some(Boolean) && !states.every(Boolean) ? " (mixed)" : "");
      }
    }
    renderLanes() {
      const nums = new Set([
        ...this.p.steps.flatMap((s) => s.cc.map((c) => c[0])),
        ...Object.keys(this.p.ccSources || {}).map(Number),
        ...(this.p.ccLanes || []),
      ]);
      if (this.lane !== "velocity" && !nums.has(+this.lane))
        this.lane = "velocity";
      this.$("lane").innerHTML = [
        ["velocity", "Velocity"],
        ...[...nums]
          .sort((a, b) => a - b)
          .map((n) => [
            String(n),
            "CC " + n + (CC_NAMES[n] ? " · " + CC_NAMES[n] : ""),
          ]),
      ]
        .map(
          ([value, label]) =>
            '<button type="button" data-lane="' +
            value +
            '" aria-pressed="' +
            (this.lane === value) +
            '" class="' +
            (this.lane === value ? "active" : "") +
            '">' +
            label +
            "</button>",
        )
        .join("");
      this.$("laneCount").textContent = this.p.drum
        ? "CC lanes are available on melodic tracks 1–3"
        : nums.size + " / 4 CC lanes";
      this.$("ccControls").hidden = this.lane === "velocity";
      this.$("removeCC").disabled = this.lane === "velocity";
      this.$("addCC").disabled = this.p.drum;
      this.$("ccNumber").disabled = this.p.drum;
      this.$("laneStatus").textContent =
        this.lane === "velocity"
          ? "Velocity controls note strength. Choose a CC number, then Add CC lane to automate a controller. Velocity stays available above."
          : "Editing CC " +
            this.lane +
            (CC_NAMES[this.lane] ? " (" + CC_NAMES[this.lane] + ")" : "") +
            ". Controller playback and recording require experimental v0.10.0-alpha.1 firmware. Velocity is unchanged.";
      this.$("laneHelp").textContent =
        this.lane === "velocity"
          ? "Drag existing bars to change note velocity. Shift-drag adjusts selected notes relatively."
          : "Click or drag the graph to create step values (0–127). Right-click removes a point; an empty step sends nothing. Source configures recording on the module, not in the browser.";
      const source = this.p.ccSources?.[this.lane];
      for (const id of ["ccSource", "ccMin", "ccMax", "ccValue"])
        this.$(id).disabled = this.lane === "velocity";
      this.$("ccSource").value = source ? String(source.input + 1) : "0";
      this.$("ccMin").value = source?.min ?? 0;
      this.$("ccMax").value = source?.max ?? 127;
      this.$("ccMin").disabled = this.lane === "velocity" || !source;
      this.$("ccMax").disabled = this.lane === "velocity" || !source;
      this.$("ccValue").value =
        this.p.steps[this.model.cursor]?.cc.find(
          (c) => c[0] === +this.lane,
        )?.[1] ?? 0;
      const lane = this.$("laneGraph"),
        previous = this.$("laneScroll").scrollLeft;
      lane.style.width = this.p.length * this.cellW + "px";
      let html = "";
      for (let s = 0; s < this.p.length; s++) {
        const pairs =
          this.lane === "velocity"
            ? this.p.steps[s].notes
            : this.p.steps[s].cc.filter((c) => c[0] === +this.lane);
        pairs.forEach(([n, v], i) => {
          const w =
            this.lane === "velocity"
              ? Math.max(4, (this.cellW - 4) / Math.max(1, pairs.length))
              : this.cellW - 4;
          html +=
            '<div class="value ' +
            ((
              this.lane === "velocity"
                ? this.model.selection.has(s + ":" + n)
                : this.ccSelection?.has(s)
            )
              ? "selected"
              : "") +
            '" data-step="' +
            s +
            '" data-value="' +
            n +
            '" style="left:' +
            (s * this.cellW + 2 + i * w) +
            "px;width:" +
            Math.max(3, w - 1) +
            "px;height:" +
            Math.max(3, (v / 127) * 98) +
            'px" title="Step ' +
            (s + 1) +
            " · " +
            (this.lane === "velocity" ? F.displayNote(n) : "CC " + n) +
            " = " +
            v +
            '">' +
            (w > 16 ? "<span>" + v + "</span>" : "") +
            "</div>";
        });
      }
      lane.innerHTML = html;
      this.$("laneScroll").scrollLeft = previous;
    }
    renderSettings() {
      if (this.$("settings").hidden) return;
      const fields = this.$("settingsFields");
      fields.innerHTML = "";
      const [project, track] = this.parts,
        key = project + "/track" + track + "/TrackSettings.txt",
        ts = this.model.settings[key] || {};
      for (const [name, label, min, max, def] of [
        ["gatelength", "Gate length (%)", 1, 100, 50],
        ["direction", "Direction", 0, 3, 0],
        ["shuffle", "Shuffle", 0, 100, 50],
        ["slide", "Slide", 0, 127, 50],
        ...(!this.p.drum
          ? [
              ["ratchet", "Ratchet amount", 0, 8, 0],
              ["humanize", "Humanize", 0, 100, 0],
            ]
          : []),
      ]) {
        const node = document.createElement("label");
        node.textContent = label + " ";
        const input = document.createElement(
          name === "direction" ? "select" : "input",
        );
        if (name === "direction") {
          ["Forward", "Reverse", "Pendulum", "Random"].forEach((text, i) => {
            const option = document.createElement("option");
            option.value = i;
            option.textContent = text;
            input.append(option);
          });
        } else input.type = "number";
        input.min = min;
        input.max = max;
        input.value =
          name === "gatelength" && this.p.drum
            ? (ts.triggerlength?.at(-1) ?? def)
            : (ts[name] ?? def);
        input.onchange = () =>
          this.action("Set " + label, () => {
            const v = +input.value;
            if (!Number.isInteger(v) || v < min || v > max)
              throw new Error(label + " must be " + min + " to " + max);
            this.model.settings[key] ||= {};
            if (name === "gatelength" && this.p.drum) {
              this.model.settings[key].triggerlength ||= Array(9).fill(50);
              this.model.settings[key].triggerlength[8] = v;
            } else this.model.settings[key][name] = v;
          });
        node.append(input);
        fields.append(node);
      }
    }
    saveViewport() {
      if (this.model.key)
        this.viewports[this.model.key] = {
          top: this.$("viewport").scrollTop,
          left: this.$("viewport").scrollLeft,
        };
    }
    restoreViewport() {
      const v = this.viewports[this.model.key];
      if (v) {
        this.$("viewport").scrollTop = v.top;
        this.$("viewport").scrollLeft = v.left;
      } else this.fitNotes();
    }
    fitNotes() {
      if (!this.p) return;
      const ns = this.p.steps.flatMap((s) => s.notes.map((n) => n[0])),
        pitch = this.p.drum
          ? 4
          : ns.length
            ? (Math.min(...ns) + Math.max(...ns)) / 2
            : 60;
      this.$("viewport").scrollTop = Math.max(
        0,
        ((this.p.drum ? 7 : 127) - pitch) * this.cellH -
          this.$("viewport").clientHeight / 2,
      );
    }
    coordinates(ev) {
      const grid = this.$("sheet").querySelector(".grid"),
        r = grid.getBoundingClientRect();
      return {
        s: Math.floor((ev.clientX - r.left) / this.cellW),
        n:
          (this.p.drum ? 7 : 127) -
          Math.floor((ev.clientY - r.top) / this.cellH),
        x: ev.clientX - r.left,
        y: ev.clientY - r.top,
      };
    }
    selectVisuals() {
      this.$("sheet")
        .querySelectorAll("[data-note]")
        .forEach((el) =>
          el.classList.toggle(
            "selected",
            this.model.selection.has(el.dataset.note),
          ),
        );
      this.renderInspector();
      this.renderLanes();
    }
    startGesture(ev) {
      if (ev.button !== 0 || this.busy) return;
      this.editingLane = false;
      const target = ev.target,
        key = target.closest("[data-pitch]");
      if (key) {
        this.audition(+key.dataset.pitch, +this.$("velocity").value);
        return;
      }
      const ruler = target.closest(".ruler");
      if (ruler) {
        const r = ruler.getBoundingClientRect(),
          s = Math.max(
            0,
            Math.min(
              this.p.length - 1,
              Math.floor((ev.clientX - r.left) / this.cellW),
            ),
          );
        this.model.cursor = s;
        if (ev.shiftKey) {
          const anchor = this.loopStart;
          this.loopStart = Math.min(anchor, s);
          this.loopEnd = Math.max(anchor, s) + 1;
        } else {
          this.loopStart = s;
          this.loopEnd = null;
        }
        this.renderRoll();
        this.renderInspector();
        return;
      }
      if (!target.closest(".grid")) return;
      ev.preventDefault();
      this.$("viewport").focus();
      const at = this.coordinates(ev);
      if (at.s < 0 || at.s >= this.p.length || at.n < 0) return;
      this.model.cursor = at.s;
      const note = target.closest("[data-note]"),
        k = at.s + ":" + at.n;
      const g = {
        before: this.model.snapshot(),
        x: ev.clientX,
        y: ev.clientY,
        start: at,
        moved: false,
        type: this.mode === "draw" ? "draw" : note ? "move" : "marquee",
        copy: ev.altKey,
        visited: new Set(),
        oldSelection: new Set(this.model.selection),
        erase: !!note,
      };
      if (g.type === "move") {
        if (ev.shiftKey) {
          if (this.model.selection.has(k)) this.model.selection.delete(k);
          else this.model.selection.add(k);
        } else if (!this.model.selection.has(k))
          this.model.selection = new Set([k]);
        g.source = this.model.notes();
      }
      if (g.type === "marquee" && !ev.shiftKey) this.model.selection.clear();
      this.gesture = g;
      this.$("viewport").setPointerCapture(ev.pointerId);
      if (g.type === "draw") this.drawAt(at);
      this.selectVisuals();
    }
    drawAt(at) {
      const g = this.gesture,
        p = this.p;
      if (at.s < 0 || at.s >= p.length || at.n < 0 || at.n > (p.drum ? 7 : 127))
        return;
      const key = at.s + ":" + at.n;
      if (g.visited.has(key)) return;
      g.visited.add(key);
      const notes = p.steps[at.s].notes,
        i = notes.findIndex((n) => n[0] === at.n);
      if (g.erase) {
        if (i >= 0) notes.splice(i, 1);
        this.model.selection.delete(key);
      } else if (i < 0) {
        if (notes.length >= 8) {
          this.toast("A step can contain at most eight notes");
          return;
        }
        notes.push([
          at.n,
          Math.max(1, Math.min(127, +this.$("velocity").value || 100)),
        ]);
        this.model.selection.add(key);
      }
      this.renderRoll();
      this.renderLanes();
    }
    moveGesture(ev) {
      const g = this.gesture;
      if (!g) return;
      const dx = ev.clientX - g.x,
        dy = ev.clientY - g.y;
      if (!g.moved && Math.hypot(dx, dy) < 4) return;
      g.moved = true;
      const v = this.$("viewport"),
        r = v.getBoundingClientRect();
      if (ev.clientX > r.right - 25) v.scrollLeft += 12;
      if (ev.clientX < r.left + 70) v.scrollLeft -= 12;
      if (ev.clientY > r.bottom - 25) v.scrollTop += 12;
      if (ev.clientY < r.top + 45) v.scrollTop -= 12;
      const at = this.coordinates(ev);
      if (g.type === "draw") {
        const prev = g.previous || g.start,
          steps = Math.max(Math.abs(at.s - prev.s), Math.abs(at.n - prev.n), 1);
        for (let i = 1; i <= steps; i++)
          this.drawAt({
            s: Math.round(prev.s + ((at.s - prev.s) * i) / steps),
            n: Math.round(prev.n + ((at.n - prev.n) * i) / steps),
          });
        g.previous = at;
        return;
      }
      if (g.type === "move") {
        this.model.restore(g.before);
        this.model.selection = new Set(g.oldSelection);
        try {
          this.model.transform(
            at.s - g.start.s,
            at.n - g.start.n,
            g.copy,
            g.source,
          );
          g.error = null;
        } catch (e) {
          g.error = e.message;
        }
        this.renderRoll();
        this.renderInspector();
        this.renderLanes();
        return;
      }
      const minS = Math.max(0, Math.min(at.s, g.start.s)),
        maxS = Math.min(this.p.length - 1, Math.max(at.s, g.start.s)),
        minN = Math.min(at.n, g.start.n),
        maxN = Math.max(at.n, g.start.n);
      this.model.selection = ev.shiftKey ? new Set(g.oldSelection) : new Set();
      for (let s = minS; s <= maxS; s++)
        for (const [n] of this.p.steps[s].notes)
          if (n >= minN && n <= maxN) this.model.selection.add(s + ":" + n);
      this.selectVisuals();
      let box = this.$("sheet").querySelector(".marquee");
      if (!box) {
        box = document.createElement("div");
        box.className = "marquee";
        this.$("sheet").querySelector(".grid").append(box);
      }
      box.style.cssText =
        "left:" +
        Math.min(at.x, g.start.x) +
        "px;top:" +
        Math.min(at.y, g.start.y) +
        "px;width:" +
        Math.abs(at.x - g.start.x) +
        "px;height:" +
        Math.abs(at.y - g.start.y) +
        "px";
    }
    endGesture(cancel = false) {
      const g = this.gesture;
      if (!g) return;
      this.gesture = null;
      this.preventDouble = !!g.moved;
      if (cancel || g.error) {
        this.model.restore(g.before);
        if (g.error) this.toast(g.error);
      } else
        this.model.commit(
          g.type === "draw"
            ? "Draw notes"
            : g.copy
              ? "Copy notes"
              : "Move notes",
          g.before,
        );
      if (g.moved || g.type === "draw" || cancel || g.error) this.renderRoll();
      this.renderInspector();
      this.renderLanes();
    }
    doubleClick(ev) {
      if (this.mode !== "pointer" || this.preventDouble) {
        this.preventDouble = false;
        return;
      }
      const at = this.coordinates(ev);
      if (
        at.s < 0 ||
        at.s >= this.p.length ||
        at.n < 0 ||
        at.n > (this.p.drum ? 7 : 127)
      )
        return;
      const k = at.s + ":" + at.n;
      this.action("Toggle note", () => {
        const ns = this.p.steps[at.s].notes,
          i = ns.findIndex((n) => n[0] === at.n);
        if (i >= 0) {
          ns.splice(i, 1);
          this.model.selection.delete(k);
        } else {
          if (ns.length === 8)
            throw new Error("A step can contain at most eight notes");
          ns.push([at.n, +this.$("velocity").value || 100]);
          this.model.selection = new Set([k]);
          this.audition(at.n, +this.$("velocity").value || 100);
        }
      });
    }
    startLane(ev) {
      if (ev.button !== 0 || this.busy) return;
      ev.preventDefault();
      this.editingLane = true;
      this.$("viewport").focus();
      const bar = ev.target.closest("[data-step]"),
        r = this.$("laneGraph").getBoundingClientRect();
      if (this.lane !== "velocity" && ev.shiftKey && bar) {
        const s = +bar.dataset.step;
        this.ccSelection ||= new Set();
        if (this.ccSelection.has(s)) this.ccSelection.delete(s);
        else this.ccSelection.add(s);
        this.model.cursor = s;
        this.renderLanes();
        return;
      }
      this.laneGesture = {
        before: this.model.snapshot(),
        rect: r,
        relative: ev.shiftKey,
        startY: ev.clientY,
        source: this.model.notes(),
        pitch: bar ? +bar.dataset.value : null,
        step: bar ? +bar.dataset.step : null,
      };
      this.$("laneGraph").setPointerCapture(ev.pointerId);
      this.moveLane(ev);
    }
    moveLane(ev) {
      const g = this.laneGesture;
      if (!g) return;
      const s = Math.max(
          0,
          Math.min(
            this.p.length - 1,
            Math.floor((ev.clientX - g.rect.left) / this.cellW),
          ),
        ),
        v = Math.max(
          this.lane === "velocity" ? 1 : 0,
          Math.min(
            127,
            Math.round(((g.rect.bottom - ev.clientY) / g.rect.height) * 127),
          ),
        );
      this.model.cursor = s;
      if (this.lane !== "velocity") {
        this.ccSelection = new Set([s]);
      }
      if (this.lane === "velocity") {
        if (g.relative && g.source.length) {
          this.model.restore(g.before);
          const d = Math.round(((g.startY - ev.clientY) / g.rect.height) * 127);
          for (const n of g.source)
            this.p.steps[n.s].notes.find((pair) => pair[0] === n.n)[1] =
              Math.max(1, Math.min(127, n.v + d));
        } else {
          const ns = this.p.steps[s].notes;
          for (const pair of ns)
            if (g.pitch === null || s !== g.step || pair[0] === g.pitch)
              pair[1] = v;
        }
      } else {
        const previous = g.last || { s, v },
          distance = Math.abs(s - previous.s),
          direction = s >= previous.s ? 1 : -1;
        for (let i = 0; i <= distance; i++) {
          const step = previous.s + i * direction,
            value = distance
              ? Math.round(previous.v + ((v - previous.v) * i) / distance)
              : v,
            ns = this.p.steps[step].cc,
            pair = ns.find((c) => c[0] === +this.lane);
          if (pair) pair[1] = value;
          else ns.push([+this.lane, value]);
        }
        g.last = { s, v };
      }
      this.renderLanes();
      this.renderInspector();
    }
    endLane(cancel = false) {
      const g = this.laneGesture;
      if (!g) return;
      this.laneGesture = null;
      if (cancel) this.model.restore(g.before);
      else
        this.model.commit(
          "Edit " + (this.lane === "velocity" ? "velocity" : "CC automation"),
          g.before,
        );
      this.renderRoll();
      this.renderLanes();
    }
    copy() {
      const notes = this.model.notes();
      if (!notes.length) return;
      const start = Math.min(...notes.map((n) => n.s));
      this.clipboard = notes.map((n) => ({ ...n, s: n.s - start }));
      this.toast("Copied " + notes.length + " notes");
    }
    paste() {
      if (!this.clipboard.length) return;
      this.action("Paste notes", () => {
        this.model.transform(this.model.cursor, 0, true, this.clipboard);
      });
    }
    duplicate() {
      const notes = this.model.notes();
      if (!notes.length) return;
      const ds =
        Math.max(...notes.map((n) => n.s)) -
        Math.min(...notes.map((n) => n.s)) +
        1;
      this.action("Duplicate notes", () =>
        this.model.transform(ds, 0, true, notes),
      );
    }
    keydown(ev) {
      const tag = ev.composedPath()[0]?.tagName;
      if (
        ["INPUT", "TEXTAREA", "SELECT"].includes(tag) ||
        this.$("dialog").open
      )
        return;
      const cmd = ev.ctrlKey || ev.metaKey,
        key = ev.key.toLowerCase();
      if (this.busy || !this.p) return;
      if (
        this.editingLane &&
        this.lane !== "velocity" &&
        this.laneKey(ev, cmd, key)
      ) {
        ev.preventDefault();
        return;
      }
      if ((this.gesture || this.laneGesture) && key !== "escape") {
        ev.preventDefault();
        return;
      }
      let handled = true;
      if (key === "escape") {
        this.endGesture(true);
        this.endLane(true);
        this.stop();
      } else if (cmd && key === "z") {
        if (ev.shiftKey) this.model.redo();
        else this.model.undo();
      } else if (cmd && key === "y") this.model.redo();
      else if (cmd && key === "s") this.guard(() => this.saveAll())();
      else if (cmd && key === "a") {
        this.model.selection = new Set(
          this.p.steps
            .slice(0, this.p.length)
            .flatMap((s, i) => s.notes.map((n) => i + ":" + n[0])),
        );
        this.selectVisuals();
      } else if (cmd && key === "c") this.copy();
      else if (cmd && key === "x") {
        this.copy();
        this.model.deleteSelection();
      } else if (cmd && key === "v") this.paste();
      else if (cmd && key === "d") this.duplicate();
      else if (key === "delete" || key === "backspace")
        this.model.deleteSelection();
      else if (key === "b") {
        this.mode = this.mode === "draw" ? "pointer" : "draw";
        this.render();
      } else if (key === " ") {
        if (this.playing) this.stop();
        else this.guard(() => this.startPlayback())();
      } else if (
        ["arrowleft", "arrowright", "arrowup", "arrowdown"].includes(key)
      ) {
        const ds = key === "arrowleft" ? -1 : key === "arrowright" ? 1 : 0,
          dn =
            key === "arrowup"
              ? ev.shiftKey
                ? 12
                : 1
              : key === "arrowdown"
                ? -(ev.shiftKey ? 12 : 1)
                : 0;
        if (this.model.selection.size)
          this.action("Nudge notes", () => this.model.transform(ds, dn));
        else {
          this.model.cursor = Math.max(
            0,
            Math.min(this.p.length - 1, this.model.cursor + ds),
          );
          this.renderRoll();
          this.renderInspector();
        }
      } else handled = false;
      if (handled) ev.preventDefault();
    }
    laneKey(ev, cmd, key) {
      const points = this.ccSelection || new Set([this.model.cursor]);
      if (cmd && key === "a") {
        this.ccSelection = new Set(
          this.p.steps
            .map((s, i) => (s.cc.some((c) => c[0] === +this.lane) ? i : null))
            .filter((i) => i !== null),
        );
        this.renderLanes();
        return true;
      }
      if (cmd && ["c", "x"].includes(key)) {
        const selected = [...points]
          .map((s) => [
            s,
            this.p.steps[s].cc.find((c) => c[0] === +this.lane)?.[1],
          ])
          .filter((p) => p[1] !== undefined);
        if (selected.length) {
          const first = Math.min(...selected.map((p) => p[0]));
          this.ccClipboard = selected.map(([s, v]) => [s - first, v]);
        }
        if (key === "x")
          this.action("Cut CC points", () => {
            for (const s of points)
              this.p.steps[s].cc = this.p.steps[s].cc.filter(
                (c) => c[0] !== +this.lane,
              );
          });
        return true;
      }
      if (cmd && key === "v") {
        if (!this.ccClipboard) return true;
        this.action("Paste CC points", () => {
          if (
            this.ccClipboard.some(
              ([s]) => s + this.model.cursor >= this.p.length,
            )
          )
            throw new Error("All CC points must fit inside the pattern");
          for (const [s, v] of this.ccClipboard) {
            const ns = this.p.steps[s + this.model.cursor].cc,
              pair = ns.find((c) => c[0] === +this.lane);
            if (pair) pair[1] = v;
            else ns.push([+this.lane, v]);
          }
        });
        return true;
      }
      if (["delete", "backspace"].includes(key)) {
        this.action("Delete CC points", () => {
          for (const s of points)
            this.p.steps[s].cc = this.p.steps[s].cc.filter(
              (c) => c[0] !== +this.lane,
            );
        });
        return true;
      }
      return false;
    }
    audioContext() {
      if (!this.audio)
        this.audio = new (window.AudioContext || window.webkitAudioContext)();
      return this.audio;
    }
    async audition(pitch, velocity) {
      if (this.p.drum) pitch = 36 + pitch * 2;
      const ctx = this.audioContext();
      await ctx.resume();
      this.voice(pitch, velocity, ctx.currentTime, 0.15, this.p.drum);
    }
    voice(pitch, velocity, time, length, drum = false) {
      const ctx = this.audioContext(),
        osc = ctx.createOscillator(),
        gain = ctx.createGain();
      osc.type = drum ? "triangle" : "sine";
      osc.frequency.setValueAtTime(440 * Math.pow(2, (pitch - 69) / 12), time);
      gain.gain.setValueAtTime(0, time);
      gain.gain.linearRampToValueAtTime((0.09 * velocity) / 127, time + 0.005);
      gain.gain.exponentialRampToValueAtTime(
        0.0001,
        time + Math.max(0.02, length),
      );
      osc.connect(gain).connect(ctx.destination);
      osc.start(time);
      osc.stop(time + Math.max(0.03, length) + 0.02);
      this.voices ||= new Set();
      this.voices.add(osc);
      osc.onended = () => this.voices.delete(osc);
    }
    async startPlayback() {
      if (this.playing || !this.p) return;
      const ctx = this.audioContext();
      await ctx.resume();
      this.playing = true;
      this.playStep = this.loopStart;
      this.nextTime = ctx.currentTime + 0.03;
      this.$("play").textContent = "Ⅱ Pause";
      this.timer = setInterval(() => this.schedule(), 20);
      this.schedule();
    }
    schedule() {
      if (!this.playing) return;
      const ctx = this.audioContext(),
        bpm = Math.max(30, Math.min(300, +this.$("bpm").value || 120));
      const ticks =
        [384, 192, 96, 48, 256, 128, 64, 32][this.p.base.duration ?? 2] || 96;
      const stepTime = ((60 / bpm / 4) * ticks) / 96;
      const trackSettings =
          this.model.settings[
            this.parts[0] + "/track" + this.parts[1] + "/TrackSettings.txt"
          ] || {},
        gate = Math.max(
          0.01,
          Math.min(1, (trackSettings.gatelength ?? 50) / 100),
        );
      while (this.nextTime < ctx.currentTime + 0.08) {
        if (this.playStep >= this.p.length)
          this.playStep = this.loopStart < this.p.length ? this.loopStart : 0;
        const s = this.playStep,
          st = this.p.steps[s],
          at = this.nextTime,
          key = this.model.key;
        for (const [n, v] of st.notes) {
          let ties = 0;
          while (
            s + ties < this.p.length - 1 &&
            this.p.steps[s + ties].modifier & 1
          )
            ties++;
          const previous = s > 0 ? this.p.steps[s - 1] : null;
          if (
            previous?.modifier & 1 &&
            previous.notes.some((pair) => pair[0] === n)
          )
            continue;
          this.voice(
            this.p.drum ? 36 + n * 2 : n,
            v,
            at,
            stepTime * (ties + gate),
            this.p.drum,
          );
        }
        const delay = Math.max(0, (at - ctx.currentTime) * 1000);
        const timer = setTimeout(() => {
          if (!this.playing || key !== this.model.key) return;
          const line = this.$("sheet").querySelector(".playhead");
          line.hidden = false;
          line.style.left = 58 + s * this.cellW + "px";
        }, delay);
        this.visualTimers ||= new Set();
        this.visualTimers.add(timer);
        setTimeout(() => this.visualTimers.delete(timer), delay + 5);
        this.nextTime += stepTime;
        this.playStep++;
        if (this.playStep >= (this.loopEnd || this.p.length)) {
          if (this.looping) this.playStep = this.loopStart;
          else {
            clearInterval(this.timer);
            this.stopTimer = setTimeout(
              () => this.stop(),
              Math.max(0, (this.nextTime - ctx.currentTime) * 1000),
            );
            break;
          }
        }
      }
    }
    stop() {
      this.playing = false;
      clearInterval(this.timer);
      clearTimeout(this.stopTimer);
      this.visualTimers?.forEach(clearTimeout);
      this.visualTimers?.clear();
      this.voices?.forEach((o) => {
        try {
          o.stop();
        } catch {}
      });
      this.voices?.clear();
      if (this.$) {
        this.$("play").textContent = "▶ Play";
        const line = this.$("sheet").querySelector(".playhead");
        if (line) line.hidden = true;
      }
    }
    wire() {
      const on = (id, fn) => {
        this.$(id).onclick = this.guard(fn);
      };
      this.shadowRoot.addEventListener("keydown", (ev) => this.keydown(ev));
      on("open", () => this.connect());
      on("save", () => this.saveAll());
      on("newProject", () => this.newProject());
      on("newPattern", () => this.newPattern());
      on("copyPattern", () => this.newPattern(true));
      on("exportFolder", () => this.exportProjectFolder());
      on("export", () =>
        this.download(
          "gc-editor-project.json",
          JSON.stringify(this.model.export(), null, 2),
          "application/json",
        ),
      );
      on("exportPattern", () =>
        this.download(
          "pattern" + this.parts[2] + ".txt",
          F.encode(this.p),
          "application/octet-stream",
        ),
      );
      on("exportNotes", async () => {
        if (
          (await this.modal(
            "Export notes only",
            "This creates a separate pattern file with notes and step flags, omitting all CC automation and CV assignments. Your editor document stays intact.",
            [
              ["cancel", "Cancel"],
              ["ok", "Export notes"],
            ],
          )) !== "ok"
        )
          return;
        const p = F.clone(this.p);
        p.steps.forEach((s) => {
          s.cc = [];
        });
        p.ccSources = {};
        p.ccLanes = [];
        this.download(
          "pattern" + this.parts[2] + ".txt",
          F.encode(p),
          "application/octet-stream",
        );
      });
      on("import", () => this.$("file").click());
      this.$("file").onchange = this.guard(async () => {
        await this.importFile(this.$("file").files[0]);
        this.$("file").value = "";
      });
      on("restore", async () => {
        const saved = localStorage.getItem("gc-editor-v2-draft");
        if (!saved) return;
        if (
          this.model.dirty &&
          (await this.modal(
            "Recover draft",
            "Replace this workspace with the saved browser draft?",
            [
              ["cancel", "Cancel"],
              ["ok", "Recover"],
            ],
          )) !== "ok"
        )
          return;
        this.model.import(JSON.parse(saved));
        this.$("restore").hidden = true;
        this.fitNotes();
      });
      on("pointer", () => {
        this.mode = "pointer";
        this.render();
      });
      on("draw", () => {
        this.mode = "draw";
        this.render();
      });
      on("undo", () => this.model.undo());
      on("redo", () => this.model.redo());
      on("duplicate", () => this.duplicate());
      on("delete", () => this.model.deleteSelection());
      on("clear", async () => {
        if (
          (await this.modal(
            "Clear pattern",
            "Remove all notes and automation from this pattern? You can undo this.",
            [
              ["cancel", "Cancel"],
              ["ok", "Clear"],
            ],
          )) === "ok"
        )
          this.action("Clear pattern", () => {
            this.p.steps = Array.from({ length: 128 }, () => ({
              notes: [],
              cc: [],
              modifier: 0,
              ratchet: 0,
            }));
            this.p.ccSources = {};
            this.p.ccLanes = [];
            if (this.p.drum)
              this.p.base.ratchets = Array.from({ length: 8 }, () =>
                Array(this.p.length).fill(0),
              );
            this.model.selection.clear();
          });
      });
      on("settingsBtn", () => {
        this.$("settings").hidden = !this.$("settings").hidden;
        this.renderSettings();
      });
      on("fit", () => this.fitNotes());
      on("fitTime", () => {
        this.cellW = Math.max(
          18,
          Math.min(80, (this.$("viewport").clientWidth - 60) / this.p.length),
        );
        this.$("zoomX").value = this.cellW;
        this.renderRoll();
        this.renderLanes();
      });
      this.$("zoomX").oninput = () => {
        this.cellW = +this.$("zoomX").value;
        this.renderRoll();
        this.renderLanes();
      };
      this.$("zoomY").oninput = () => {
        const pitch =
          (this.p.drum ? 7 : 127) -
          (this.$("viewport").scrollTop + this.$("viewport").clientHeight / 2) /
            this.cellH;
        this.cellH = +this.$("zoomY").value;
        this.renderRoll();
        this.$("viewport").scrollTop =
          ((this.p.drum ? 7 : 127) - pitch) * this.cellH -
          this.$("viewport").clientHeight / 2;
      };
      this.$("length").onchange = () => {
        const n = +this.$("length").value;
        this.action("Set pattern length", () => {
          if (
            n < this.p.length &&
            this.p.steps.slice(n).some((s) => s.notes.length || s.cc.length)
          )
            throw new Error(
              "Clear notes and automation beyond the new end before shortening the pattern",
            );
          this.p.length = n;
          this.model.cursor = Math.min(this.model.cursor, n - 1);
          this.loopStart = 0;
          this.loopEnd = null;
        });
      };
      this.$("selectedVel").onchange = () =>
        this.action("Set velocity", () => {
          const v = +this.$("selectedVel").value;
          if (!Number.isInteger(v) || v < 1 || v > 127)
            throw new Error("Velocity must be 1 to 127");
          for (const { s, n } of this.model.notes())
            this.p.steps[s].notes.find((pair) => pair[0] === n)[1] = v;
        });
      for (const [id, mask] of [
        ["tie", 1],
        ["slide", 2],
        ["ratchet", 0],
      ])
        on(id, () =>
          this.action("Set " + id, () => {
            const steps = this.selectedSteps(),
              all = steps.every((s) =>
                id === "ratchet"
                  ? this.p.steps[s].ratchet
                  : this.p.steps[s].modifier & mask,
              );
            for (const s of steps) {
              if (id === "ratchet") this.p.steps[s].ratchet = all ? 0 : 1;
              else
                this.p.steps[s].modifier = all
                  ? this.p.steps[s].modifier & ~mask
                  : this.p.steps[s].modifier | mask;
            }
          }),
        );
      this.$("duration").onchange = () => {
        const duration = +this.$("duration").value;
        this.action("Set step duration", () => {
          this.p.base.duration = duration;
        });
      };
      this.$("lane").onclick = (ev) => {
        const button = ev.target.closest("[data-lane]");
        if (!button) return;
        this.lane = button.dataset.lane;
        this.ccSelection = new Set();
        this.renderLanes();
      };
      on("addCC", () => {
        const n = +this.$("ccNumber").value;
        if (!Number.isInteger(n) || n < 0 || n > 127)
          throw new Error("CC must be 0 to 127");
        const nums = new Set([
          ...this.p.steps.flatMap((s) => s.cc.map((c) => c[0])),
          ...Object.keys(this.p.ccSources || {}).map(Number),
          ...(this.p.ccLanes || []),
        ]);
        if (!nums.has(n) && nums.size >= F.MAX_CC)
          throw new Error("A track supports at most four CC lanes");
        if (this.p.drum)
          throw new Error("CC lanes belong to melodic tracks 1–3");
        this.action("Add CC lane", () => {
          this.p.ccLanes ||= [];
          if (!this.p.ccLanes.includes(n)) this.p.ccLanes.push(n);
        });
        this.extraLanes.add(n);
        this.lane = String(n);
        this.renderLanes();
      });
      on("removeCC", async () => {
        if (this.lane === "velocity") return;
        const n = +this.lane;
        if (
          (await this.modal(
            "Remove CC " + n,
            "Remove all points in this controller lane? You can undo this.",
            [
              ["cancel", "Cancel"],
              ["ok", "Remove"],
            ],
          )) !== "ok"
        )
          return;
        this.action("Remove CC lane", () => {
          this.p.steps.forEach((s) => {
            s.cc = s.cc.filter((c) => c[0] !== n);
          });
          if (this.p.ccSources) delete this.p.ccSources[n];
          this.p.ccLanes = (this.p.ccLanes || []).filter(
            (number) => number !== n,
          );
        });
        this.extraLanes.delete(n);
        this.lane = "velocity";
        this.renderLanes();
      });
      const vp = this.$("viewport");
      vp.addEventListener("pointerdown", (ev) => this.startGesture(ev));
      vp.addEventListener("pointermove", (ev) => this.moveGesture(ev));
      vp.addEventListener("pointerup", () => this.endGesture());
      vp.addEventListener("pointercancel", () => this.endGesture(true));
      vp.addEventListener("dblclick", (ev) => this.doubleClick(ev));
      vp.addEventListener("scroll", () => {
        this.$("laneScroll").scrollLeft = vp.scrollLeft;
      });
      vp.addEventListener("contextmenu", (ev) => {
        const note = ev.target.closest("[data-note]");
        if (!note) return;
        ev.preventDefault();
        this.model.selection = new Set([note.dataset.note]);
        this.model.deleteSelection();
      });
      const lane = this.$("laneGraph");
      lane.addEventListener("pointerdown", (ev) => this.startLane(ev));
      lane.addEventListener("pointermove", (ev) => this.moveLane(ev));
      lane.addEventListener("pointerup", () => this.endLane());
      lane.addEventListener("pointercancel", () => this.endLane(true));
      lane.addEventListener("contextmenu", (ev) => {
        if (this.lane === "velocity") return;
        ev.preventDefault();
        const r = lane.getBoundingClientRect(),
          s = Math.floor((ev.clientX - r.left) / this.cellW);
        if (s >= 0 && s < this.p.length)
          this.action("Remove CC point", () => {
            this.p.steps[s].cc = this.p.steps[s].cc.filter(
              (c) => c[0] !== +this.lane,
            );
          });
      });
      this.$("laneScroll").addEventListener("scroll", () => {
        const n = this.$("laneScroll").scrollLeft;
        if (Math.abs(vp.scrollLeft - n) > 1) vp.scrollLeft = n;
      });
      this.$("bpm").onchange = () =>
        this.action("Set tempo", () => {
          const v = +this.$("bpm").value;
          if (!Number.isInteger(v) || v < 30 || v > 300)
            throw new Error("Tempo must be 30 to 300 BPM");
          const key = this.parts[0] + "/ProjectSettings.txt";
          this.model.settings[key] ||= {};
          this.model.settings[key].BPM = v;
        });
      this.$("ccSource").onchange = () =>
        this.action("Set CC recording source", () => {
          this.p.ccSources ||= {};
          const input = +this.$("ccSource").value;
          if (input)
            this.p.ccSources[this.lane] = {
              input: input - 1,
              min: 0,
              max: 127,
            };
          else delete this.p.ccSources[this.lane];
        });
      for (const [id, key] of [
        ["ccMin", "min"],
        ["ccMax", "max"],
      ])
        this.$(id).onchange = () =>
          this.action("Set CV range", () => {
            this.p.ccSources[this.lane][key] = +this.$(id).value;
          });
      this.$("ccValue").onchange = () =>
        this.action("Set CC value", () => {
          const st = this.p.steps[this.model.cursor],
            v = +this.$("ccValue").value,
            pair = st.cc.find((c) => c[0] === +this.lane);
          if (pair) pair[1] = v;
          else st.cc.push([+this.lane, v]);
        });
      on("play", () => (this.playing ? this.stop() : this.startPlayback()));
      on("stop", () => this.stop());
      on("loop", () => {
        this.looping = !this.looping;
        this.$("loop").classList.toggle("active", this.looping);
      });
    }
  }
  if (!customElements.get("gc-editor"))
    customElements.define("gc-editor", GCEditor);
})();
