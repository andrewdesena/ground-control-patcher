/* Download-only firmware builder. Verification gates every output. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id),
    catalog = window.GCRelease,
    core = window.GCFirmware;
  let release = catalog;
  let input = null,
    output = null,
    generation = 0,
    verified = false;
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
    $("buildStatus").textContent = "";
    progress(1);
  };
  function progress(step) {
    for (let i = 1; i <= 4; i++)
      $("progress" + i).classList.toggle("current", i === step);
  }
  async function takeFile(file) {
    if (!file) return;
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
    if (!verified || !input) return;
    const token = generation;
    output = null;
    $("build").disabled = true;
    $("dl").disabled = true;
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
        hash,
      };
      $("dl").disabled = false;
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
  function download() {
    if (!output) return;
    const url = URL.createObjectURL(
        new Blob([output.text], { type: "text/plain" }),
      ),
      a = document.createElement("a");
    a.href = url;
    a.download = output.name;
    a.click();
    progress(4);
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
    $("downloadFilename").textContent = release.filename;
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
  $("dl").onclick = download;
  $("firmwareTab").onclick = () => showView("patcher");
  $("editorTab").onclick = () => showView("editor");
  window.__gcShowView = showView;
  window.GCModder = {
    ...core,
    ready: true,
    takeFile,
    build,
    getOutput: () => output,
  };
  if (location.hash === "#editor") showView("editor");
})();
