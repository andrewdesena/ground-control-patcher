/* Ground Control pattern editor — <gc-editor> web component (shadow DOM, isolated CSS).
   Embedded as the "Editor" tab of the patcher. Full-range DAW piano roll (MIDI 0–127),
   left vertical track bar (Tracks 1/2/3/D), no octave control. */
(function () {
  "use strict";
  const NAME = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"];
  const isBlack = n => NAME[n % 12].includes("#");
  const noteName = n => NAME[n % 12] + (Math.floor(n / 12) - 1);
  const nameToMidi = s => s ? (parseInt(s.slice(-1), 10) + 1) * 12 + NAME.indexOf(s.slice(0, -1)) : null;

  const CSS = `
  :host{display:block;color:#e7e9ec;font:13px/1.4 ui-monospace,Menlo,monospace;
    --bg:#0d0f12;--panel:#15181d;--panel2:#1b1f26;--line:#2a2f38;--fg:#e7e9ec;--muted:#8b93a1;
    --accent:#ff3b3b;--accent2:#28d7c3;--key:#12151a;--drum:#ffb04d;}
  *{box-sizing:border-box}
  header{display:flex;gap:10px;align-items:center;padding:9px 12px;border-bottom:1px solid var(--line);
    background:var(--panel);flex-wrap:wrap;border-radius:8px 8px 0 0}
  h1{font-size:12px;margin:0;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);white-space:nowrap}
  .grp{display:flex;gap:6px;align-items:center}
  label{color:var(--muted);font-size:11px}
  input[type=number],input[type=text]{background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:4px;padding:3px 6px;font:inherit}
  button{background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:4px;padding:5px 9px;font:inherit;cursor:pointer}
  button:hover{border-color:var(--accent)}
  button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
  #app{display:flex;border:1px solid var(--line);border-top:0;border-radius:0 0 8px 8px;overflow:hidden;background:var(--bg)}
  #side{flex:0 0 76px;display:flex;flex-direction:column;gap:6px;padding:8px 6px;border-right:1px solid var(--line);background:var(--panel)}
  #side .ttab{text-align:left;padding:8px 7px;font-size:11px;line-height:1.1}
  #side .ttab.active{border-color:var(--accent2);color:var(--accent2)}
  #side .ttab.d.active{border-color:var(--drum);color:var(--drum)}
  #main{flex:1;min-width:0;padding:10px;display:flex;flex-direction:column}
  .hint{color:var(--muted);font-size:11px;margin:0 0 8px}
  .vscroll{overflow:auto;border:1px solid var(--line);border-radius:6px;max-height:64vh;background:#0b0d10}
  .row{display:flex;align-items:stretch}
  .key{position:sticky;left:0;z-index:3;flex:0 0 56px;height:16px;display:flex;align-items:center;justify-content:flex-end;
    padding-right:6px;font-size:10px;color:var(--muted);background:var(--panel);border-bottom:1px solid #191c22;border-right:1px solid var(--line)}
  .key.black{background:#0a0c0f;color:#5b6270}
  .steps-hdr{display:flex;position:sticky;top:0;z-index:4;background:var(--panel);border-bottom:1px solid var(--line)}
  .steps-hdr .spacer{flex:0 0 56px;position:sticky;left:0;z-index:5;background:var(--panel)}
  .scell{flex:0 0 20px;width:20px;text-align:center;font-size:9px;color:var(--muted);border-right:1px solid #191c22;padding:2px 0}
  .scell.beat{color:var(--accent2);font-weight:700}
  .cell{flex:0 0 20px;width:20px;height:16px;border-right:1px solid #191c22;border-bottom:1px solid #191c22;background:var(--key);cursor:pointer}
  .cell.beat{border-left:1px solid #343b47}.cell.bar{background:#0f1217}.cell.blackrow{background:#0a0c0f}
  .cell:hover{outline:1px solid var(--accent2);outline-offset:-1px}
  .cell.on{background:var(--accent)!important}
  .dcell.on{background:var(--drum)!important}
  .dlane{display:flex}
  .dlabel{flex:0 0 56px;height:20px;display:flex;align-items:center;justify-content:flex-end;padding-right:6px;font-size:10px;color:var(--drum);border-bottom:1px solid #191c22;background:var(--panel);position:sticky;left:0;z-index:3}
  .dcell{width:20px;height:20px;flex:0 0 20px;border-right:1px solid #191c22;border-bottom:1px solid #191c22;background:var(--key);cursor:pointer}
  .dcell.beat{border-left:1px solid #343b47}.dcell:hover{outline:1px solid var(--drum);outline-offset:-1px}
  .lanes{margin-top:10px}
  .lane{display:flex;align-items:center;gap:8px;margin:6px 0;border:1px solid var(--line);border-radius:6px;padding:8px;background:var(--panel)}
  .ccbar{display:flex;gap:2px;overflow:auto}
  .cc{width:20px;height:50px;background:var(--key);border:1px solid #191c22;position:relative;cursor:pointer;border-radius:2px;overflow:hidden;flex:0 0 20px}
  .cc .fill{position:absolute;bottom:0;left:0;right:0;background:var(--accent2);opacity:.75}
  .cc .lbl{position:absolute;top:1px;left:0;right:0;text-align:center;font-size:8px;color:#0d0f12}
  #drawer{position:fixed;top:0;right:0;height:100%;width:340px;max-width:92vw;background:var(--panel);border-left:1px solid var(--line);
    transform:translateX(100%);transition:transform .18s ease;z-index:60;display:flex;flex-direction:column;color:var(--fg)}
  #drawer.open{transform:translateX(0)}
  .dhead{display:flex;justify-content:space-between;align-items:center;gap:6px;padding:10px 12px;border-bottom:1px solid var(--line)}
  .dbody{overflow:auto;padding:10px 12px;flex:1}
  .sec{margin-bottom:14px}.sec h3{font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:var(--accent2);margin:6px 0}
  .fld{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:2px 0}
  .fld span{color:var(--muted);font-size:11px}.fld input,.fld select{width:120px}
  .arr4{display:flex;gap:3px}.arr4 input{width:32px!important}
  .drawerTab.active{color:var(--accent);border-color:var(--accent)}
  .grp select{background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:4px;padding:4px 6px;font:inherit;max-width:180px}
  #sdstat{color:var(--muted);font-size:10px;max-width:170px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .cell.sel{outline:2px solid #fff;outline-offset:-2px;z-index:1}
  #ccHost{margin-top:6px}
  .cclane{display:flex;align-items:stretch;border:1px solid var(--line);border-radius:6px;margin:6px 0;overflow:hidden;background:#0b0d10}
  .cchead{flex:0 0 56px;position:sticky;left:0;z-index:3;background:var(--panel);border-right:1px solid var(--line);display:flex;flex-direction:column;align-items:center;justify-content:center;font-size:10px;color:var(--accent2);gap:4px;padding:4px 2px}
  .cchead button{font-size:9px;padding:1px 4px}
  .ccsvg{flex:1;min-width:0;display:block;cursor:crosshair}
  .ccsvg circle{fill:var(--accent2);stroke:#04342c;stroke-width:1;cursor:ns-resize}
  .ccsvg polyline{fill:none;stroke:var(--accent2);stroke-width:1.5;opacity:.8}
  .ccsvg .cgrid{stroke:#1c2230;stroke-width:1}`;

  const TPL = `
  <header>
    <h1>GC Pattern Editor</h1>
    <div class="grp"><label>Steps</label><input id="stepsNum" type="number" min="1" max="128" value="32" style="width:62px"></div>
    <div class="grp"><label>Vel</label><input id="vel" type="number" min="1" max="127" value="100" style="width:52px"><button id="applyVel" title="Apply Vel to selected notes">▸ sel</button></div>
    <div class="grp" style="margin-left:auto">
      <button id="settingsBtn">Settings</button>
      <button id="clear">Clear track</button>
      <button id="importBtn">Import</button><input id="importFile" type="file" accept=".json" hidden>
      <button id="exportBtn" class="primary">Export project</button>
    </div>
    <div class="grp" style="margin-left:8px">
      <button id="connectSD">Connect SD</button>
      <select id="sdfiles" hidden></select>
      <button id="saveSD" disabled>Save to SD</button>
      <span id="sdstat"></span>
    </div>
  </header>
  <div id="app">
    <div id="side"></div>
    <div id="main"><div class="hint" id="hint"></div><div id="rollWrap"></div>
      <div id="ccSection"><div class="grp" id="ccCtl"><label>CC lane</label>
        <input id="ccAdd" type="number" min="0" max="127" value="74" style="width:60px">
        <button id="addCC">Add lane</button>
        <span style="color:var(--muted);font-size:10px">click a lane to add a point · drag points · right-click removes</span>
      </div><div id="ccHost"></div></div>
      <div class="lanes" id="lanes"></div></div>
  </div>
  <div id="drawer"><div class="dhead"><strong style="color:var(--accent)">Settings</strong>
    <div class="grp" id="drawerTabs"></div><button id="closeDrawer">✕</button></div>
    <div class="dbody" id="drawerBody"></div></div>`;

  class GCEditor extends HTMLElement {
    connectedCallback() {
      if (this._init) return; this._init = true;
      const r = this.attachShadow({ mode: "open" });
      this._r = r;
      r.innerHTML = `<style>${CSS}</style>${TPL}`;
      const $ = id => r.querySelector("#" + id);
      this.$ = $;

      const MELODIC = [1, 2, 3], DRUM = 8;
      const state = { steps: 32, track: 1, melodic: {}, drum: [], tset: {}, global: {}, cv: {}, drawerTab: "Global", sel: new Set(), ccLanes: [], pasteStep: 0 };
      const ensureMelodic = t => {
        if (!state.melodic[t]) { state.melodic[t] = []; for (let i = 0; i < 128; i++) state.melodic[t].push({ notes: [], cc: [], modifier: 0, ratchet: 0 }); }
        return state.melodic[t];
      };
      const ensureDrum = () => { while (state.drum.length < 128) state.drum.push({ pads: {}, ratchet: 0, modifier: 0 }); return state.drum; };

      const F = (k, label, def, type = "num", extra = {}) => Object.assign({ k, label, def, type }, extra);
      const GLOBAL_FIELDS = [
        F("BPM", "BPM", 120, "num", { min: 30, max: 300 }), F("MasterClockSource", "Clock src", 0, "sel", { opts: ["Internal", "Jack", "USB", "MIDI"] }),
        F("OutputClockDivider", "Out clk div", 0, "num", { min: 0, max: 16 }), F("ResetOutputMode", "Reset mode", 0, "num", { min: 0, max: 3 }),
        F("ClockOnStop", "Clock on stop", 0, "num", { min: 0, max: 1 }), F("RxTransport", "Rx transport", 1, "num", { min: 0, max: 1 }),
        F("TxTransport", "Tx transport", 1, "num", { min: 0, max: 1 }), F("KeyLed", "Key LED", 1, "num", { min: 0, max: 1 }),
        F("GateLed", "Gate LED", 1, "num", { min: 0, max: 1 }), F("MenuTimeout", "Menu timeout", 10, "num", { min: 0, max: 120 }),
        F("TapTempo", "Tap tempo", 2, "num", { min: 1, max: 8 }), F("StartPattern", "Start pattern", 0, "num", { min: 0, max: 23 }),
        F("SnapAlgo", "Snap algo", 0, "num", { min: 0, max: 3 }), F("MidiHostLoopback", "Host loopback", 0, "num", { min: 0, max: 1 }),
        F("MidiHostToDeviceForward", "Host→Dev fwd", 0, "num", { min: 0, max: 1 }), F("MidiDeviceToHostForward", "Dev→Host fwd", 0, "num", { min: 0, max: 1 }),
        F("TracksLocked", "Tracks locked", 0, "num", { min: 0, max: 1 }), F("BuzzerEnabled", "Buzzer", 0, "num", { min: 0, max: 1 }),
        F("BuzzerTrack", "Buzzer track", 0, "num", { min: 0, max: 12 }), F("channelTx", "MIDI TX ch[4]", 0, "arr4", { min: 1, max: 16, defArr: [1, 2, 3, 4] }),
        F("channelRx", "MIDI RX ch[4]", 0, "arr4", { min: 1, max: 16, defArr: [1, 2, 3, 4] }), F("enableTx", "Enable TX[4]", 0, "arr4", { min: 0, max: 1, defArr: [1, 1, 1, 1] }),
        F("enableRx", "Enable RX[4]", 0, "arr4", { min: 0, max: 1, defArr: [1, 1, 1, 1] }), F("OmniChannel", "Omni[4]", 0, "arr4", { min: 0, max: 1, defArr: [0, 0, 0, 0] })
      ];
      const TRACK_FIELDS = [
        F("Scale", "Scale", 0, "sel", { opts: ["Chromatic", "Major", "Minor", "PentaMaj", "PentaMin", "Dorian", "Drum"] }), F("Root", "Root", 0, "num", { min: 0, max: 11 }),
        F("direction", "Direction", 0, "sel", { opts: ["Forward", "Reverse", "Pendulum", "Random"] }), F("shuffle", "Shuffle", 0, "num", { min: 0, max: 100 }),
        F("humanize", "Humanize", 0, "num", { min: 0, max: 100 }), F("ratchet", "Ratchet", 0, "num", { min: 0, max: 8 }),
        F("gatelength", "Gate length", 64, "num", { min: 0, max: 127 }), F("slide", "Slide", 0, "num", { min: 0, max: 127 }),
        F("ArpEngaged", "Arp engaged", 0, "num", { min: 0, max: 1 }), F("ArpMode", "Arp mode", 0, "num", { min: 0, max: 7 }),
        F("ArpLatch", "Arp latch", 0, "num", { min: 0, max: 1 }), F("ArpSuperLatch", "Arp super-latch", 0, "num", { min: 0, max: 1 }),
        F("modulationTrack", "Mod track", 0, "num", { min: 0, max: 3 }), F("modulationSubtrack", "Mod subtrack", 0, "num", { min: 0, max: 3 }),
        F("PolyFrom", "Polyrhythm from", 1, "num", { min: 1, max: 32 }), F("PolyTo", "Polyrhythm to", 1, "num", { min: 1, max: 32 })
      ];
      const CV_FIELDS = [F("Type", "Type", 0, "sel", { opts: ["Off", "Pattern shift", "Semitone", "Octave", "Shuffle", "Ratchets", "Slide", "Gate len", "CC", "Pattern"] }), F("Param", "Param", 0, "num", { min: 0, max: 127 })];
      const defVal = f => f.type === "arr4" ? (f.defArr || [0, 0, 0, 0]).slice() : (f.def !== undefined ? f.def : 0);
      (function seed() {
        for (const f of GLOBAL_FIELDS) if (state.global[f.k] === undefined) state.global[f.k] = defVal(f);
        for (let c = 1; c <= 4; c++) { if (!state.cv[c]) state.cv[c] = {}; for (const f of CV_FIELDS) if (state.cv[c][f.k] === undefined) state.cv[c][f.k] = defVal(f); }
        for (const t of MELODIC.concat(["D"])) { if (!state.tset[t]) state.tset[t] = {}; for (const f of TRACK_FIELDS) if (state.tset[t][f.k] === undefined) state.tset[t][f.k] = defVal(f); }
      })();

      // ---- melodic (full 0..127 piano roll) ----
      const NS = "http://www.w3.org/2000/svg";
      const noteIndex = (step, pitch) => ensureMelodic(state.track)[step].notes.findIndex(p => p[0] === pitch);
      const cellOn = (step, pitch) => noteIndex(step, pitch) >= 0;
      const keyOf = (s, p) => s + ":" + p;
      const noteAt = (s, p) => { const i = noteIndex(s, p); return i >= 0 ? ensureMelodic(state.track)[s].notes[i] : null; };
      const isSel = (s, p) => state.sel.has(keyOf(s, p));
      const velColor = v => { v = Math.max(0, Math.min(127, v | 0)); const l = 28 + 36 * (v / 127); return "hsl(356,72%," + l.toFixed(0) + "%)"; };
      function selectOrToggle(s, p, ev) {
        const list = ensureMelodic(state.track)[s].notes, i = list.findIndex(x => x[0] === p), k = keyOf(s, p);
        state.pasteStep = s;
        if (i < 0) { list.push([p, +$("vel").value || 100]); state.sel = new Set([k]); }
        else if (ev && ev.shiftKey) { if (state.sel.has(k)) state.sel.delete(k); else state.sel.add(k); }
        else state.sel = new Set([k]);
        paint();
      }
      function removeNote(s, p) { const list = ensureMelodic(state.track)[s].notes, i = list.findIndex(x => x[0] === p); if (i >= 0) { list.splice(i, 1); state.sel.delete(keyOf(s, p)); paint(); } }
      const toggleNote = (s, p) => { const st = ensureMelodic(state.track)[s], i = noteIndex(s, p); if (i >= 0) st.notes.splice(i, 1); else st.notes.push([p, +$("vel").value]); paint(); };
      const setCCval = (s, num, v) => { const st = ensureMelodic(state.track)[s]; v = Math.max(0, Math.min(127, v | 0)); const i = st.cc.findIndex(c => c[0] === num); if (i >= 0) st.cc[i][1] = v; else st.cc.push([num, v]); };
      const delCCval = (s, num) => { const st = ensureMelodic(state.track)[s]; const i = st.cc.findIndex(c => c[0] === num); if (i >= 0) st.cc.splice(i, 1); };
      const setCC = (s, num, val) => { if (val === null) delCCval(s, num); else setCCval(s, num, val); buildCC(); };

      function buildMelodic() {
        const w = $("rollWrap"); w.innerHTML = "";
        const vs = document.createElement("div"); vs.className = "vscroll";
        const hdr = document.createElement("div"); hdr.className = "steps-hdr";
        const sp = document.createElement("div"); sp.className = "spacer"; hdr.appendChild(sp);
        for (let s = 0; s < state.steps; s++) { const d = document.createElement("div"); d.className = "scell" + (s % 4 === 0 ? " beat" : ""); d.textContent = (s % 4 === 0) ? (s + 1) : ""; hdr.appendChild(d); }
        vs.appendChild(hdr);
        for (let pitch = 127; pitch >= 0; pitch--) {
          const row = document.createElement("div"); row.className = "row";
          const k = document.createElement("div"); k.className = "key" + (isBlack(pitch) ? " black" : ""); k.textContent = noteName(pitch); row.appendChild(k);
          for (let s = 0; s < state.steps; s++) {
            const c = document.createElement("div");
            const nv = noteAt(s, pitch);
            c.className = "cell" + (isBlack(pitch) ? " blackrow" : "") + (s % 4 === 0 ? " beat" : "") + (s % 16 === 0 ? " bar" : "") + (isSel(s, pitch) ? " sel" : "");
            if (nv) c.style.background = velColor(nv[1]);
            c.addEventListener("click", ev => selectOrToggle(s, pitch, ev));
            c.addEventListener("contextmenu", ev => { ev.preventDefault(); removeNote(s, pitch); });
            row.appendChild(c);
          }
          vs.appendChild(row);
        }
        w.appendChild(vs);
        // center on middle C-ish
        requestAnimationFrame(() => { vs.scrollTop = (127 - 60) * 16 - 120; });
        buildCC();
      }
      function buildCC() {
        const host = $("ccHost"); if (!host) return; host.innerHTML = "";
        const mc = ensureMelodic(state.track), W = state.steps * 20, H = 64;
        state.ccLanes.forEach(num => {
          const lane = document.createElement("div"); lane.className = "cclane";
          const head = document.createElement("div"); head.className = "cchead";
          head.appendChild(document.createTextNode("CC " + num));
          const xb = document.createElement("button"); xb.textContent = "✕";
          xb.onclick = () => { state.ccLanes = state.ccLanes.filter(n => n !== num); buildCC(); };
          head.appendChild(xb); lane.appendChild(head);
          const svg = document.createElementNS(NS, "svg");
          svg.setAttribute("class", "ccsvg"); svg.setAttribute("viewBox", "0 0 " + W + " " + H);
          svg.setAttribute("width", W); svg.setAttribute("height", H);
          for (let s = 0; s <= state.steps; s += 4) { const ln = document.createElementNS(NS, "line"); ln.setAttribute("class", "cgrid"); ln.setAttribute("x1", s * 20); ln.setAttribute("y1", 0); ln.setAttribute("x2", s * 20); ln.setAttribute("y2", H); svg.appendChild(ln); }
          const pts = [];
          for (let s = 0; s < state.steps; s++) { const e = mc[s].cc.find(c => c[0] === num); if (e) pts.push([s, e[1]]); }
          const yOf = v => H - 3 - (v / 127) * (H - 8);
          if (pts.length > 1) { const pl = document.createElementNS(NS, "polyline"); pl.setAttribute("points", pts.map(([s, v]) => (s * 20 + 10) + "," + yOf(v)).join(" ")); svg.appendChild(pl); }
          pts.forEach(([s, v]) => {
            const c = document.createElementNS(NS, "circle"); c.setAttribute("cx", s * 20 + 10); c.setAttribute("cy", yOf(v)); c.setAttribute("r", 4);
            c.addEventListener("pointerdown", ev => {
              ev.preventDefault(); ev.stopPropagation();
              const rect = svg.getBoundingClientRect();
              const move = e2 => { const y = e2.clientY - rect.top; const val = Math.round((H - 3 - Math.max(0, Math.min(H - 8, y))) / (H - 8) * 127); setCCval(s, num, val); buildCC(); };
              const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
              window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
            });
            c.addEventListener("contextmenu", ev => { ev.preventDefault(); ev.stopPropagation(); delCCval(s, num); buildCC(); });
            svg.appendChild(c);
          });
          svg.addEventListener("click", ev => {
            if (ev.target !== svg) return;
            const rect = svg.getBoundingClientRect();
            const s = Math.max(0, Math.min(state.steps - 1, Math.floor((ev.clientX - rect.left) / 20)));
            const y = ev.clientY - rect.top;
            const val = Math.round((H - 3 - Math.max(0, Math.min(H - 8, y))) / (H - 8) * 127);
            setCCval(s, num, val); buildCC();
          });
          lane.appendChild(svg); host.appendChild(lane);
        });
        if (!state.ccLanes.length) { const e = document.createElement("div"); e.className = "hint"; e.textContent = "No CC lanes. Pick a CC# above and Add lane to draw automation."; host.appendChild(e); }
      }

      // ---- drum ----
      const toggleDrum = (step, pad) => { const d = ensureDrum()[step]; if (d.pads[pad] !== undefined) delete d.pads[pad]; else d.pads[pad] = +$("vel").value; paint(); };
      function buildDrum() {
        const w = $("rollWrap"); w.innerHTML = "";
        const vs = document.createElement("div"); vs.className = "vscroll";
        const hdr = document.createElement("div"); hdr.className = "steps-hdr";
        const sp = document.createElement("div"); sp.className = "spacer"; hdr.appendChild(sp);
        for (let s = 0; s < state.steps; s++) { const d = document.createElement("div"); d.className = "scell" + (s % 4 === 0 ? " beat" : ""); d.textContent = (s % 4 === 0) ? (s + 1) : ""; hdr.appendChild(d); }
        vs.appendChild(hdr);
        const drum = ensureDrum();
        for (let pad = 1; pad <= DRUM; pad++) {
          const ln = document.createElement("div"); ln.className = "dlane";
          const lb = document.createElement("div"); lb.className = "dlabel"; lb.textContent = "Drum " + pad; ln.appendChild(lb);
          for (let s = 0; s < state.steps; s++) { const c = document.createElement("div"); c.className = "dcell" + (s % 4 === 0 ? " beat" : "") + (drum[s].pads[pad] !== undefined ? " on" : ""); c.addEventListener("click", () => toggleDrum(s, pad)); ln.appendChild(c); }
          vs.appendChild(ln);
        }
        w.appendChild(vs);
        $("lanes").innerHTML = '<div class="lane"><label>Drum map</label><span style="color:#8b93a1">38,40,41,43,45,47,48,50 (pads 1-8)</span></div>';
      }

      // ---- left track bar ----
      function buildTrackbar() {
        const t = $("side"); t.innerHTML = "";
        [["1", "Track 1"], ["2", "Track 2"], ["3", "Track 3"], ["D", "Track D"]].forEach(([v, label]) => {
          const b = document.createElement("button"); b.className = "ttab" + (state.track === v ? " active" : "") + (v === "D" ? " d" : "");
          b.textContent = label; b.onclick = () => { state.track = v; state.sel = new Set(); paint(); }; t.appendChild(b);
        });
        const g = document.createElement("div"); g.style.cssText = "margin-top:auto;color:#8b93a1;font-size:10px;padding:6px 2px"; g.textContent = "128 steps · MIDI 0–127"; t.appendChild(g);
      }
      function paint() {
        buildTrackbar();
        const isD = state.track === "D";
        $("hint").textContent = isD ? "Track D (drums): click a lane cell to place a trigger." : "Click to add/select · shift-click multi-select · right-click deletes · drag CC points to draw automation · Ctrl/Cmd C/V copies notes.";
        const cs = $("ccSection"); if (cs) cs.style.display = isD ? "none" : "";
        if (isD) buildDrum(); else buildMelodic();
      }

      // ---- settings drawer ----
      function renderFields(fields, store, onChange) {
        const frag = document.createDocumentFragment();
        for (const f of fields) {
          const row = document.createElement("div"); row.className = "fld";
          const lbl = document.createElement("span"); lbl.textContent = f.label; row.appendChild(lbl);
          if (f.type === "sel") {
            const s = document.createElement("select"); f.opts.forEach((o, i) => { const op = document.createElement("option"); op.value = i; op.textContent = o; s.appendChild(op); });
            s.value = store[f.k]; s.onchange = () => { store[f.k] = +s.value; onChange && onChange(); }; row.appendChild(s);
          } else if (f.type === "arr4") {
            const wrap = document.createElement("div"); wrap.className = "arr4"; const arr = store[f.k] || (store[f.k] = defVal(f));
            for (let i = 0; i < 4; i++) { const inp = document.createElement("input"); inp.type = "number"; inp.min = f.min; inp.max = f.max; inp.value = arr[i]; inp.onchange = () => { arr[i] = +inp.value; onChange && onChange(); }; wrap.appendChild(inp); }
            row.appendChild(wrap);
          } else {
            const inp = document.createElement("input"); inp.type = "number"; if (f.min !== undefined) inp.min = f.min; if (f.max !== undefined) inp.max = f.max;
            inp.value = store[f.k]; inp.onchange = () => { store[f.k] = +inp.value; onChange && onChange(); }; row.appendChild(inp);
          }
          frag.appendChild(row);
        }
        return frag;
      }
      function buildDrawer() {
        const tabs = $("drawerTabs"); tabs.innerHTML = "";
        ["Global", "Track", "CV"].forEach(name => { const b = document.createElement("button"); b.className = "drawerTab" + (state.drawerTab === name ? " active" : ""); b.textContent = name; b.onclick = () => { state.drawerTab = name; buildDrawer(); }; tabs.appendChild(b); });
        const body = $("drawerBody"); body.innerHTML = "";
        if (state.drawerTab === "Global") { const sec = document.createElement("div"); sec.className = "sec"; sec.innerHTML = "<h3>Project / Global</h3>"; sec.appendChild(renderFields(GLOBAL_FIELDS, state.global)); body.appendChild(sec); }
        else if (state.drawerTab === "Track") { const which = state.track === "D" ? "D" : state.track; const sec = document.createElement("div"); sec.className = "sec"; sec.innerHTML = "<h3>" + (state.track === "D" ? "Drum Track" : "Track " + which) + " settings</h3>"; sec.appendChild(renderFields(TRACK_FIELDS, state.tset[which])); body.appendChild(sec); }
        else { for (let c = 1; c <= 4; c++) { const sec = document.createElement("div"); sec.className = "sec"; sec.innerHTML = "<h3>Ext CV " + c + "</h3>"; sec.appendChild(renderFields(CV_FIELDS, state.cv[c])); body.appendChild(sec); } }
      }

      // ---- export / import ----
      function trackObj(t) {
        const src = ensureMelodic(t).slice(0, state.steps).map(s => ({ modifier: s.modifier || 0, ratchet: s.ratchet || 0, notes: s.notes.map(p => [p[0], p[1]]), cc: s.cc.map(c => [c[0], c[1]]) }));
        const legacy = src.map(s => { if (!s.notes.length) return { note: "", velocity: 0, modifier: s.modifier, ratchet: s.ratchet }; const lo = s.notes.reduce((a, b) => b[0] < a[0] ? b : a, s.notes[0]); return { note: noteName(lo[0]), velocity: lo[1], modifier: s.modifier, ratchet: s.ratchet }; });
        const ts = state.tset[t];
        return { index: t, scale: { Scale: ts.Scale, Root: ts.Root },
          settings: { direction: ts.direction, slide: ts.slide, shuffle: ts.shuffle, humanize: ts.humanize, ratchet: ts.ratchet, gatelength: ts.gatelength },
          arp: { Engaged: ts.ArpEngaged, Mode: ts.ArpMode, Latch: ts.ArpLatch, SuperLatch: ts.ArpSuperLatch },
          polyrhythm: { From: ts.PolyFrom, To: ts.PolyTo }, modulation: { track: ts.modulationTrack, subtrack: ts.modulationSubtrack },
          step_limit: state.steps, steps2: src, steps: legacy, ratchets: src.map(s => s.ratchet) };
      }
      function drumObj() { const d = ensureDrum().slice(0, state.steps); const map = [38, 40, 41, 43, 45, 47, 48, 50];
        return { lanes: DRUM, map, steps: d.map((st, idx) => ({ index: idx, triggers: Object.entries(st.pads).map(([pad, vel]) => ({ pad: +pad, note: map[pad - 1], velocity: vel })), ratchet: st.ratchet || 0, modifier: st.modifier || 0 })) }; }
      function exportJSON() { return JSON.stringify({ app: "gc-pattern-editor", version: 2, steps: state.steps, store: "steps2",
        global: Object.assign({}, state.global), cv: [1, 2, 3, 4].map(c => ({ Type: state.cv[c].Type, Param: state.cv[c].Param })),
        tracks: MELODIC.map(trackObj), drum: drumObj() }, null, 2); }
      function doExport() { const blob = new Blob([exportJSON()], { type: "application/json" }); const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "gc-project.json"; a.click(); URL.revokeObjectURL(a.href); }
      function doImport(text) {
        const doc = JSON.parse(text);
        if (doc.steps) { state.steps = Math.max(1, Math.min(128, doc.steps)); $("stepsNum").value = state.steps; }
        if (doc.global) Object.assign(state.global, doc.global);
        if (doc.cv) doc.cv.forEach((c, i) => { state.cv[i + 1] = Object.assign(state.cv[i + 1] || {}, { Type: c.Type, Param: c.Param }); });
        state.melodic = {}; state.drum = []; ensureDrum();
        for (const tr of (doc.tracks || [])) { const arr = ensureMelodic(tr.index); const src2 = tr.steps2 || (tr.steps || []).map(s => ({ modifier: s.modifier || 0, ratchet: s.ratchet || 0, notes: s.note ? [[nameToMidi(s.note), s.velocity || 0]] : [], cc: [] }));
          for (let i = 0; i < src2.length && i < 128; i++) { arr[i] = { modifier: src2[i].modifier || 0, ratchet: src2[i].ratchet || 0, notes: (src2[i].notes || []).map(p => [p[0], p[1]]), cc: (src2[i].cc || []).map(c => [c[0], c[1]]) }; }
          const ts = state.tset[tr.index] || (state.tset[tr.index] = {}); if (tr.scale) { ts.Scale = tr.scale.Scale; ts.Root = tr.scale.Root; } if (tr.settings) Object.assign(ts, tr.settings); if (tr.polyrhythm) { ts.PolyFrom = tr.polyrhythm.From; ts.PolyTo = tr.polyrhythm.To; } }
        if (doc.drum && doc.drum.steps) { const dm = ensureDrum(); for (const st of doc.drum.steps) { if (st.index >= 128) continue; const tgt = { pads: {}, ratchet: st.ratchet || 0, modifier: st.modifier || 0 }; for (const trg of (st.triggers || [])) tgt.pads[trg.pad] = trg.velocity; dm[st.index] = tgt; } }
        const ccNums = new Set();
        for (const t of MELODIC) { const arr = ensureMelodic(t); for (let i = 0; i < state.steps; i++) arr[i].cc.forEach(c => ccNums.add(c[0])); }
        if (ccNums.size) state.ccLanes = [...ccNums].sort((a, b) => a - b);
        state.sel = new Set();
        paint(); if ($("drawer").classList.contains("open")) buildDrawer();
      }

      // ---- SD card (File System Access) ----
      let sdDir = window.__gcSD || null, lastProjectName = 'gc-project.json';
      const sdstat = $("sdstat");
      async function refreshSD() {
        if (!sdDir) return;
        const sel = $("sdfiles"); sel.innerHTML = "";
        const names = [];
        try { for await (const e of sdDir.values()) if (e.kind === 'file' && /\.json$/i.test(e.name)) names.push(e.name); }
        catch (e) { sdstat.textContent = 'list err: ' + e.message; return; }
        names.sort();
        const o0 = document.createElement('option'); o0.value = ''; o0.textContent = names.length ? 'Open…' : '(no .json on card)'; sel.appendChild(o0);
        for (const n of names) { const o = document.createElement('option'); o.value = n; o.textContent = n; sel.appendChild(o); }
        sel.hidden = false;
      }
      $("connectSD").onclick = async () => {
        if (!window.showDirectoryPicker) { sdstat.textContent = 'needs Chrome/Edge over https'; return; }
        try {
          sdDir = window.__gcSD || await window.showDirectoryPicker({ mode: 'readwrite' });
          window.__gcSD = sdDir;
          sdstat.textContent = 'SD: ' + sdDir.name;
          $("saveSD").disabled = false;
          await refreshSD();
        } catch (e) { if (!e || e.name !== 'AbortError') sdstat.textContent = 'err: ' + e.message; }
      };
      $("sdfiles").onchange = async (ev) => {
        const name = ev.target.value; if (!name || !sdDir) return;
        try { const fh = await sdDir.getFileHandle(name); doImport(await (await fh.getFile()).text()); lastProjectName = name; sdstat.textContent = 'opened ' + name; }
        catch (e) { sdstat.textContent = 'open err: ' + e.message; }
      };
      $("saveSD").onclick = async () => {
        if (!sdDir) { sdstat.textContent = 'connect SD first'; return; }
        let name = prompt('Save project on SD as', lastProjectName || 'gc-project.json'); if (!name) return;
        if (!/\.json$/i.test(name)) name += '.json';
        try { const fh = await sdDir.getFileHandle(name, { create: true }); const w = await fh.createWritable(); await w.write(exportJSON()); await w.close(); lastProjectName = name; sdstat.textContent = 'saved ' + name; await refreshSD(); }
        catch (e) { sdstat.textContent = 'save err: ' + e.message; }
      };
      if (sdDir) { $("saveSD").disabled = false; sdstat.textContent = 'SD: ' + sdDir.name; refreshSD(); }

      // ---- wire ----
      $("applyVel").onclick = () => {
        if (state.track === "D") return;
        const v = Math.max(1, Math.min(127, +$("vel").value || 100));
        const arr = ensureMelodic(state.track);
        state.sel.forEach(k => { const [s, p] = k.split(":").map(Number); const x = arr[s].notes.find(q => q[0] === p); if (x) x[1] = v; });
        paint();
      };
      $("addCC").onclick = () => { const num = Math.max(0, Math.min(127, +$("ccAdd").value || 0)); if (!state.ccLanes.includes(num)) state.ccLanes.push(num); buildCC(); };
      let clip = null;
      window.addEventListener("keydown", ev => {
        if (!this.isConnected) return;
        const t = (ev.composedPath && ev.composedPath()[0]) || {}; const tag = (t.tagName || "").toUpperCase();
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
        if (state.track === "D") return;
        if ((ev.ctrlKey || ev.metaKey) && (ev.key === "c" || ev.key === "C")) {
          const arr = ensureMelodic(state.track); let minS = Infinity; const got = [];
          state.sel.forEach(k => { const [s, p] = k.split(":").map(Number); const n = arr[s].notes.find(q => q[0] === p); if (n) { got.push([s, p, n[1]]); if (s < minS) minS = s; } });
          if (got.length) { clip = got.map(([s, p, v]) => [s - minS, p, v]); state.pasteStep = minS; ev.preventDefault(); }
        } else if ((ev.ctrlKey || ev.metaKey) && (ev.key === "v" || ev.key === "V")) {
          if (!clip || !clip.length) return;
          const arr = ensureMelodic(state.track), dest = state.pasteStep || 0;
          clip.forEach(([ds, p, v]) => { const s = dest + ds; if (s >= 0 && s < state.steps) { if (!arr[s].notes.find(q => q[0] === p)) arr[s].notes.push([p, v]); } });
          paint(); ev.preventDefault();
        }
      });
      $("stepsNum").onchange = e => { state.steps = Math.max(1, Math.min(128, +e.target.value || 1)); e.target.value = state.steps; paint(); };
      $("clear").onclick = () => { if (state.track === "D") { state.drum = []; ensureDrum(); } else { state.melodic[state.track] = null; ensureMelodic(state.track); } paint(); };
      $("exportBtn").onclick = doExport;
      $("importBtn").onclick = () => $("importFile").click();
      $("importFile").onchange = e => { const f = e.target.files[0]; if (!f) return; const rd = new FileReader(); rd.onload = () => doImport(rd.result); rd.readAsText(f); };
      $("settingsBtn").onclick = () => { $("drawer").classList.toggle("open"); if ($("drawer").classList.contains("open")) buildDrawer(); };
      $("closeDrawer").onclick = () => $("drawer").classList.remove("open");

      for (const t of MELODIC) ensureMelodic(t); ensureDrum(); paint();
      // tiny API for tests
      this._api = { state, exportJSON, toggleNote, toggleDrum, setCC, setCCval, delCCval, selectOrToggle, removeNote, paint, buildCC, noteName, nameToMidi };
    }
  }
  if (!customElements.get("gc-editor")) customElements.define("gc-editor", GCEditor);
})();
