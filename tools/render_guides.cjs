/* Rebuild public PDF guides from the same HTML used on the website. */
const path = require("node:path");
const { spawn } = require("node:child_process");
let pw;
try {
  pw = require("playwright");
} catch {
  if (!process.env.PLAYWRIGHT_PATH)
    throw new Error("Install dev dependencies or set PLAYWRIGHT_PATH");
  pw = require(process.env.PLAYWRIGHT_PATH);
}
(async () => {
  let browser;
  const server = spawn(
    "python3",
    ["-m", "http.server", "8877", "--bind", "127.0.0.1"],
    { cwd: path.resolve(__dirname, ".."), stdio: "ignore" },
  );
  try {
    browser = await pw.chromium.launch({
      channel: process.env.GC_BROWSER || "chrome",
      headless: true,
    });
    const page = await browser.newPage();
    for (const slug of ["guide", "quick-card", "editor"]) {
      let ready = false;
      for (let i = 0; i < 20 && !ready; i++) {
        try {
          await page.goto(
            "http://127.0.0.1:8877/docs/reference/" + slug + ".html",
          );
          ready = true;
        } catch {
          await new Promise((r) => setTimeout(r, 100));
        }
      }
      if (!ready) throw new Error("Documentation server did not start");
      await page.evaluate(() => {
        const base = document.createElement("base");
        base.href =
          "https://andrewdesena.github.io/ground-control-patcher/docs/reference/";
        document.head.prepend(base);
      });
      for (const [format, suffix] of [
        ["Letter", "letter"],
        ["A4", "a4"],
      ]) {
        const dest = path.resolve(
          __dirname,
          "../docs/reference/" + slug + "-" + suffix + ".pdf",
        );
        await page.pdf({ path: dest, format, printBackground: true });
        console.log(dest);
      }
    }
  } finally {
    await browser?.close();
    server.kill();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
