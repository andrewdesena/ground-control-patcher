/* Guided installer. Verification gates every output and resets on input changes. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id),
    catalog = window.GCRelease,
    core = window.GCFirmware;
  let release = catalog;
  let input = null,
    output = null,
    dir = null,
    generation = 0,
    verified = false,
    writing = false;
  const say = (message) => {
    $("log").textContent += "\n" + message;
  };
  const banner = (message) => {
    $("banner").textContent = message;
    $("banner").hidden = !message;
  };
  const invalidate = () => {
    output = null;
    verified = false;
    input = null;
    $("build").disabled = true;
    $("dl").disabled = true;
    $("install").disabled = true;
    $("buildStatus").textContent = "";
    progress(1);
    $("finish").hidden = true;
  };
  function progress(step) {
    for (let i = 1; i <= 4; i++)
      $("progress" + i).classList.toggle("current", i === step);
  }
  async function takeFile(file) {
    if (!file || writing) return;
    const token = ++generation;
    invalidate();
    banner("");
    progress(1);
    $("verification").className = "result";
    $("verification").textContent = "Verifying " + file.name + "…";
    try {
      const candidate = new core.HexFile(await file.text());
      core.identify(candidate);
      const hash = await core.canonicalHash(candidate);
      if (token !== generation) return;
      if (!hash)
        throw new Error(
          "SHA-256 verification is unavailable. Open this page on HTTPS or localhost.",
        );
      if (hash !== release.baseHash)
        throw new Error(
          "This is not the supported stock v3.26 image. Choose the original vendor firmware.",
        );
      input = candidate;
      verified = true;
      if (release === catalog.candidate)
        banner(
          "Experimental CC candidate. Hardware validation pending. Test on a backed-up card and retain v0.9.0 for rollback.",
        );
      $("build").disabled = false;
      $("verification").className = "result success";
      $("verification").textContent =
        file.name + " · Verified stock Ground Control v3.26";
      $("log").textContent =
        "Stock canonical SHA-256: " +
        hash +
        "\nRelease: " +
        release.version +
        "\nBundle SHA-256: " +
        release.bundleHash;
      progress(2);
    } catch (e) {
      if (token !== generation) return;
      invalidate();
      $("verification").className = "result error";
      $("verification").textContent = e.message;
    }
  }
  async function build() {
    if (!verified || !input || writing) return;
    const token = generation;
    output = null;
    $("build").disabled = true;
    $("dl").disabled = true;
    $("install").disabled = true;
    try {
      const work = new core.HexFile(input.toString()),
        result = core.applyBundle(work, release.patchBundle),
        text = work.toString();
      new core.HexFile(text);
      const hash = await core.canonicalHash(work);
      if (token !== generation) return;
      output = {
        text,
        name: release.filename,
        cardName: release.cardFilename,
        hash,
      };
      $("dl").disabled = false;
      $("install").disabled = !dir;
      $("buildStatus").textContent = " Ready: v" + release.version;
      $("buildStatus").className = "result success";
      say(
        result.report.length +
          " patch sites applied. Output reparsed successfully.",
      );
      say("Output canonical SHA-256: " + hash);
      progress(3);
    } catch (e) {
      output = null;
      banner("Build stopped: " + e.message);
    } finally {
      if (token === generation) $("build").disabled = !verified;
    }
  }
  async function connectSD() {
    if (!window.showDirectoryPicker) {
      banner(
        "Direct card access needs Chrome or Edge on HTTPS or localhost. Download the HEX and copy it to the card root instead.",
      );
      return null;
    }
    try {
      dir = await window.showDirectoryPicker({ mode: "readwrite" });
      window.__gcSD = dir;
      window.dispatchEvent(
        new CustomEvent("gc-card-connected", { detail: dir }),
      );
      $("sdStatus").textContent = "Connected: " + dir.name;
      $("install").disabled = !output;
      return dir;
    } catch (e) {
      if (e.name !== "AbortError") banner("Could not connect: " + e.message);
      return null;
    }
  }
  async function install() {
    if (!dir || !output || writing) return;
    const built = output,
      target = dir;
    writing = true;
    $("install").disabled = true;
    $("build").disabled = true;
    $("drop").disabled = true;
    $("connectSD").disabled = true;
    $("releaseSelect").disabled = true;
    try {
      const conflicts = [];
      for await (const entry of target.values())
        if (
          entry.kind === "file" &&
          /\.hex$/i.test(entry.name) &&
          !entry.name.startsWith("._") &&
          entry.name.toLowerCase() !== built.cardName.toLowerCase()
        )
          conflicts.push(entry.name);
      if (conflicts.length)
        throw new Error(
          "Other firmware files are at the card root: " +
            conflicts.join(", ") +
            ". Move them off the card, then try again.",
        );
      const hasProject = [];
      for await (const entry of target.values())
        if (entry.kind === "directory" && /^project/i.test(entry.name))
          hasProject.push(entry.name);
      if (!hasProject.length)
        throw new Error(
          "This folder does not look like a Ground Control card root. Choose the root containing your project folders.",
        );
      writing = true;
      $("install").disabled = true;
      $("build").disabled = true;
      $("drop").disabled = true;
      $("connectSD").disabled = true;
      $("releaseSelect").disabled = true;
      const bytes = new TextEncoder().encode(built.text),
        handle = await target.getFileHandle(built.cardName, { create: true }),
        stream = await handle.createWritable();
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
        await (await handle.getFile()).arrayBuffer(),
      );
      if (
        readback.length !== bytes.length ||
        readback.some((b, i) => b !== bytes[i])
      )
        throw new Error("The saved firmware did not match the built file");
      $("sdStatus").textContent =
        "Verified " +
        built.cardName +
        " · " +
        bytes.length.toLocaleString() +
        " bytes";
      $("finish").hidden = false;
      banner("");
      progress(4);
    } catch (e) {
      banner("Firmware was not verified: " + e.message);
    } finally {
      writing = false;
      $("install").disabled = !output || !dir;
      $("build").disabled = !verified;
      $("drop").disabled = false;
      $("connectSD").disabled = false;
      $("releaseSelect").disabled = false;
    }
  }
  function download() {
    if (!output) return;
    const url = URL.createObjectURL(
        new Blob([output.text], { type: "text/plain" }),
      ),
      a = document.createElement("a");
    a.href = url;
    a.download = output.name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function showView(view) {
    $("viewPatcher").hidden = view !== "patcher";
    $("viewEditor").hidden = view !== "editor";
    for (const [id, v] of [
      ["firmwareTab", "patcher"],
      ["editorTab", "editor"],
    ]) {
      $(id).classList.toggle("active", v === view);
      $(id).setAttribute("aria-pressed", String(v === view));
    }
    if (view !== "editor") document.querySelector("gc-editor")?.stop?.();
    else
      requestAnimationFrame(() =>
        document.querySelector("gc-editor")?.restoreViewport?.(),
      );
    history.replaceState(
      null,
      "",
      view === "editor" ? "#editor" : location.pathname,
    );
  }
  function renderRelease() {
    $("releaseVersion").textContent = "v" + release.version;
    $("cardFilename").textContent = release.cardFilename;
    $("releaseLabel").textContent = release.label;
    for (const [id, items] of [
      ["features", release.features],
      ["limitations", release.limitations],
    ]) {
      $(id).textContent = "";
      for (const text of items) {
        const li = document.createElement("li");
        li.textContent = text;
        $(id).append(li);
      }
    }
    $("releaseSelect").disabled = writing;
    $("install").title = "Writes " + release.cardFilename + " to the card root";
    if (release === catalog.candidate)
      banner(
        "Experimental CC candidate: emulator-tested only. Physical CV mapping, timing under load, and power-cycle behavior still need testing. Keep v0.9.0 for rollback.",
      );
    else banner("");
  }
  $("releaseSelect").onchange = async () => {
    const file = $("file").files[0];
    generation++;
    invalidate();
    release =
      $("releaseSelect").value === "candidate" ? catalog.candidate : catalog;
    renderRelease();
    if (file) await takeFile(file);
  };
  renderRelease();
  $("capability").textContent = window.showDirectoryPicker
    ? "Card access is available. Select the card root, not a project folder."
    : "This browser supports file import and download. Direct SD card writes require Chrome or Edge on HTTPS or localhost.";
  $("drop").onclick = () => $("file").click();
  $("file").onchange = () => takeFile($("file").files[0]);
  for (const type of ["dragenter", "dragover"])
    $("drop").addEventListener(type, (ev) => {
      ev.preventDefault();
      $("drop").classList.add("hot");
    });
  for (const type of ["dragleave", "drop"])
    $("drop").addEventListener(type, (ev) => {
      ev.preventDefault();
      $("drop").classList.remove("hot");
      if (type === "drop") takeFile(ev.dataTransfer.files[0]);
    });
  $("build").onclick = build;
  $("connectSD").onclick = connectSD;
  $("install").onclick = install;
  $("dl").onclick = download;
  $("firmwareTab").onclick = () => showView("patcher");
  $("editorTab").onclick = () => showView("editor");
  window.addEventListener("gc-card-connected", (ev) => {
    dir = ev.detail;
    $("sdStatus").textContent = "Connected: " + dir.name;
    $("install").disabled = !output;
  });
  window.__gcShowView = showView;
  window.GCModder = {
    ...core,
    ready: true,
    takeFile,
    build,
    getOutput: () => output,
    connectSD,
    getSD: () => dir,
    installFirmware: install,
  };
  if (location.hash === "#editor") showView("editor");
})();
