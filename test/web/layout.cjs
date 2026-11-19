/* Viewport and expanded-roll integration checks. No vendor image required. */
const assert = require("node:assert/strict");
let pw;
try {
  pw = require("playwright");
} catch {
  pw = require(process.env.PLAYWRIGHT_PATH);
}
(async () => {
  const browser = await pw.chromium.launch({
    channel: "chrome",
    headless: true,
  });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const fits = async () => {
      const size = await page.evaluate(() => ({
        height: innerHeight,
        width: innerWidth,
        scroll: document.documentElement.scrollHeight,
        scrollWidth: document.documentElement.scrollWidth,
      }));
      assert.ok(size.scroll <= size.height + 1, JSON.stringify(size));
      assert.ok(size.scrollWidth <= size.width, JSON.stringify(size));
    };
    for (const [width, height] of [
      [1280, 720],
      [1366, 768],
      [1440, 900],
      [1024, 768],
    ]) {
      await page.setViewportSize({ width, height });
      await page.goto("http://127.0.0.1:8765");
      await page.waitForFunction(() => window.GCModder?.ready);
      await fits();
      assert.equal(await page.locator("#finish").isVisible(), true);
      await page.locator("#releaseSelect").selectOption("candidate");
      await fits();
      await page.locator('[data-info="releaseInfo"]').click();
      assert.equal(await page.locator("#patcherInfo").isVisible(), true);
      await fits();
      assert.ok(await page.locator("#limitations").textContent());
      await page.locator("#closePatcherInfo").click();
      await page.locator('[data-info="diagnosticsInfo"]').click();
      assert.equal(await page.locator("#log").isVisible(), true);
      await page.keyboard.press("Escape");
      await page.locator("#editorTab").click();
      const e = page.locator("gc-editor");
      await e.locator("#viewport").waitFor({ state: "visible" });
      await fits();
      await e.locator("#addCC").click();
      if (width === 1280) {
        for (const cc of [1, 7, 11]) {
          await e.locator("#ccNumber").fill(String(cc));
          await e.locator("#addCC").click();
        }
      }
      await fits();
      const roll = await e.locator("#viewport").boundingBox(),
        lane = await e.locator("#laneGraph").boundingBox();
      assert.ok(roll.height >= 150, JSON.stringify({ width, height, roll }));
      assert.ok(lane.y + lane.height <= height);
      await e.locator("#settingsBtn").click();
      await fits();
      await e.locator("#closeSettings").click();
      await e.locator("#laneInstructions").click();
      assert.ok((await e.locator("#dialogText").textContent()).includes("CC"));
      await e
        .locator("#dialog")
        .getByRole("button", { name: "Got it", exact: true })
        .click();
      // Wheel input changes the roll, never the outer page.
      await page.mouse.move(roll.x + 100, roll.y + 100);
      await page.mouse.wheel(0, 120);
      await page.waitForTimeout(80);
      assert.equal(await page.evaluate(() => scrollY), 0);
      const center = () =>
        e.evaluate(
          (el) =>
            el.$("viewport").scrollTop + el.$("viewport").clientHeight / 2,
        );
      let before = await center();
      await e.locator("#expandRoll").click();
      await page.waitForFunction(
        () => document.querySelector("gc-editor").expanded,
      );
      assert.ok(
        (await e.locator("#viewport").boundingBox()).height > roll.height + 100,
      );
      assert.equal(await e.locator("aside").isVisible(), false);
      if (width === 1366) {
        await page.evaluate(
          () =>
            new Promise((resolve) =>
              requestAnimationFrame(() => requestAnimationFrame(resolve)),
            ),
        );
        await e.evaluate((el) => {
          el.$("viewport").scrollTop += 80;
        });
        before = await center();
      }
      await page.keyboard.press("Escape");
      await page.waitForFunction(
        () =>
          !document.querySelector("gc-editor").expanded &&
          !document.fullscreenElement,
      );
      await page.waitForTimeout(80);
      assert.ok(
        Math.abs((await center()) - before) <= 2,
        JSON.stringify({ width, height, before, after: await center() }),
      );
      await fits();
    }
    const e = page.locator("gc-editor");
    await e.evaluate((el) => {
      el.requestFullscreen = async () => {
        throw new Error("Fullscreen unavailable");
      };
    });
    await e.locator("#expandRoll").click();
    assert.equal(await e.evaluate((el) => el.expanded), true);
    assert.equal(await page.evaluate(() => document.fullscreenElement), null);
    await e.locator("#expandRoll").click();
    assert.equal(await e.evaluate((el) => el.expanded), false);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator("#firmwareTab").click();
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    await page.locator("#editorTab").click();
    await e.locator("#expandRoll").click();
    assert.ok((await e.locator("#viewport").boundingBox()).height > 200);
    await e.locator("#expandRoll").click();
    assert.deepEqual(errors, []);
    console.log(
      "PASS desktop viewport fit, warning/CC/settings states, contained roll scrolling, native fullscreen/Escape, fallback expansion, pitch preservation and mobile layout",
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
