const assert = require("node:assert/strict");
let playwright;
try {
  playwright = require("playwright");
} catch {
  if (!process.env.PLAYWRIGHT_PATH)
    throw new Error("Install dev dependencies or set PLAYWRIGHT_PATH");
  playwright = require(process.env.PLAYWRIGHT_PATH);
}
const { chromium } = playwright;
(async () => {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  await page.addInitScript(() => {
    window.__firmwarePickerCalls = 0;
    window.showDirectoryPicker = () => {
      window.__firmwarePickerCalls++;
      throw new Error("The firmware patcher must not request SD access");
    };
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("http://127.0.0.1:8765");
  await page.waitForSelector("gc-editor", { state: "attached" });
  await page.screenshot({ path: "/tmp/gc-firmware.png", fullPage: true });
  await page.locator("#viewPatcher #file").setInputFiles("testdata/gc326.hex");
  await page.waitForFunction(() => !document.getElementById("build").disabled);
  await page.click("#build");
  await page.waitForFunction(() => !!window.GCModder.getOutput());
  assert.equal(
    await page.evaluate(() => GCModder.getOutput().name),
    "GCV326B0.HEX",
  );
  assert.equal(await page.locator("#viewPatcher #connectSD").count(), 0);
  assert.equal(await page.locator("#viewPatcher #install").count(), 0);
  assert.equal(
    await page.evaluate(() => typeof GCModder.installFirmware),
    "undefined",
  );
  assert.equal(
    await page.evaluate(() => typeof GCModder.connectSD),
    "undefined",
  );
  assert.equal(await page.evaluate(() => typeof GCModder.getSD), "undefined");
  const downloadEvent = page.waitForEvent("download");
  await page.locator("#viewPatcher #dl").click();
  const download = await downloadEvent;
  assert.equal(download.suggestedFilename(), "GCV326B0.HEX");
  const downloaded = require("node:fs").readFileSync(
    await download.path(),
    "utf8",
  );
  assert.equal(
    downloaded,
    await page.evaluate(() => GCModder.getOutput().text),
  );
  assert.equal(await page.evaluate(() => window.__firmwarePickerCalls), 0);
  await page.click("#editorTab");
  const e = page.locator("gc-editor");
  await e.locator("#viewport").waitFor({ state: "visible" });
  const pos = async (s, n) =>
    page.evaluate(
      ({ s, n }) => {
        const e = document.querySelector("gc-editor"),
          g = e.shadowRoot.querySelector(".grid").getBoundingClientRect();
        return {
          x: g.left + (s + 0.5) * e.cellW,
          y: g.top + (127 - n + 0.5) * e.cellH,
        };
      },
      { s, n },
    );
  let p = await pos(1, 60);
  await page.mouse.dblclick(p.x, p.y);
  assert.equal(
    await e.evaluate((el) => el.model.pattern.steps[1].notes[0][0]),
    60,
  );
  let q = await pos(3, 62);
  await page.mouse.move(p.x, p.y);
  await page.mouse.down();
  await page.mouse.move(q.x, q.y, { steps: 8 });
  await page.mouse.up();
  assert.deepEqual(await e.evaluate((el) => el.model.pattern.steps[3].notes), [
    [62, 100],
  ]);
  await page.keyboard.press("Meta+z");
  assert.deepEqual(await e.evaluate((el) => el.model.pattern.steps[1].notes), [
    [60, 100],
  ]);
  await page.keyboard.press("Meta+Shift+z");
  assert.deepEqual(await e.evaluate((el) => el.model.pattern.steps[3].notes), [
    [62, 100],
  ]);
  q = await pos(3, 62);
  await page.mouse.click(q.x, q.y);
  await e.locator("#selectedVel").fill("77");
  await e.locator("#selectedVel").dispatchEvent("change");
  assert.equal(
    await e.evaluate((el) => el.model.pattern.steps[3].notes[0][1]),
    77,
  );
  await e.locator("#viewport").focus();
  await page.keyboard.press("b");
  p = await pos(5, 60);
  q = await pos(7, 60);
  await page.mouse.move(p.x, p.y);
  await page.mouse.down();
  await page.mouse.move(q.x, q.y, { steps: 12 });
  await page.mouse.up();
  assert.equal(
    await e.evaluate((el) => el.model.pattern.steps[6].notes[0][0]),
    60,
  );
  await e.locator("#addCC").click();
  await e.locator("#laneGraph").scrollIntoViewIfNeeded();
  const lane = await e.locator("#laneGraph").boundingBox();
  await page.mouse.click(lane.x + 36 * 2 + 10, lane.y + 80);
  assert.ok(await e.evaluate((el) => el.model.pattern.steps[2].cc.length));
  assert.equal(await e.evaluate((el) => el.model.dirty), true);
  await page.screenshot({ path: "/tmp/gc-editor.png", fullPage: true });
  assert.deepEqual(errors, []);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "/tmp/gc-editor-mobile.png", fullPage: true });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
    true,
  );
  await browser.close();
  console.log(
    "PASS download-only firmware (no SD APIs/picker), exact HEX download, insert/move/undo, velocity, paint, CC and responsive layout",
  );
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
