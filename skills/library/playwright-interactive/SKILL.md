---
name: playwright-interactive
displayName: "Playwright Interactive"
version: "1.0.0"
description: Persistent Playwright debugging for local Web and Electron apps through js_repl, combining code-level inspection with visual QA.
updated_at: "2026-03-06"

triggers:
  keywords:
    - "playwright-interactive"
    - "interactive playwright"
    - "playwright debug"
    - "visual qa"
    - "electron debug"
    - "web debug"
  auto_trigger: true
  confidence_threshold: 0.72

tools:
  required:
    - js_repl
  optional:
    - Read
    - Write
    - Bash

permissions:
  level: "full"
---

# Playwright Interactive

Use a persistent `js_repl` Playwright session to debug local Web and Electron apps without tearing down the whole toolchain after every edit. This skill is for fast iterative work where Codex must alternate between code-level inspection and visual QA in the same session.

## When To Use

Use this skill when:

- You need both DOM or process inspection and screenshot-based visual review.
- The target is a local Web app or Electron app.
- You expect multiple edit -> reload -> verify loops in one session.
- The user cares about visible polish, layout fit, or interaction timing, not only script success.

Do not use this skill when:

- A one-shot static HTML check is enough.
- The task is pure API, CLI, or backend verification with no meaningful UI.
- `js_repl` is unavailable and cannot be enabled.

## Preconditions

- `js_repl` must be enabled for the current Codex session.
- Run the workflow from the workspace that contains the app you need to debug.
- Prefer `danger-full-access` sandbox mode for Playwright + Electron work.
- Keep the app's dev server alive in a persistent terminal session when the UI depends on one.
- Treat `js_repl_reset` as recovery only. A reset destroys the live Playwright handles.

If `js_repl` is missing, enable it in `~/.codex/config.toml`:

```toml
[features]
js_repl = true
```

## One-Time Setup

Run setup from the target workspace:

```bash
test -f package.json || npm init -y
npm install playwright
node -e "import('playwright').then(() => console.log('playwright import ok')).catch((error) => { console.error(error); process.exit(1); })"
```

Optional extras:

- Web-only headed Chromium: `npx playwright install chromium`
- Electron app workspace: `npm install --save-dev electron`

## Core Rules

- Keep one persistent session and reuse the same handles.
- Separate functional QA from visual QA. Passing one does not imply the other.
- Use real input for signoff: click, keyboard, touch, drag, hover.
- `page.evaluate(...)` and `electronApp.evaluate(...)` are diagnostic tools, not signoff input.
- For Electron, reload only for renderer changes. Relaunch for main-process, preload, or startup changes.
- Build one shared QA inventory from requirements, implemented UI behavior, and final claims. Signoff must map back to that inventory.

## Bootstrap Once

```javascript
var chromium;
var electronLauncher;
var browser;
var context;
var page;
var electronApp;
var appWindow;

({ chromium, _electron: electronLauncher } = await import("playwright"));
console.log("Playwright loaded");
```

Use `var` so later `js_repl` cells can reuse the same bindings.

## Web Session

Prefer `127.0.0.1` over `localhost` for local servers.

```javascript
var TARGET_URL = "http://127.0.0.1:3000";

var ensureWebBrowser = async function () {
  if (browser && !browser.isConnected()) {
    browser = undefined;
    context = undefined;
    page = undefined;
  }
  browser ??= await chromium.launch({ headless: false });
  return browser;
};

await ensureWebBrowser();
context ??= await browser.newContext({
  viewport: { width: 1600, height: 900 },
});
page ??= await context.newPage();

await page.goto(TARGET_URL, { waitUntil: "domcontentloaded" });
console.log("Loaded:", await page.title());
```

For a renderer-only code change:

```javascript
await page.reload({ waitUntil: "domcontentloaded" });
```

## Electron Session

Launch Electron from `js_repl` so the same session owns the process.

```javascript
var ELECTRON_ENTRY = ".";

if (!appWindow && electronApp) {
  await electronApp.close().catch(() => {});
  electronApp = undefined;
}

electronApp ??= await electronLauncher.launch({
  args: [ELECTRON_ENTRY],
});

appWindow ??= await electronApp.firstWindow();
console.log("Loaded Electron window:", await appWindow.title());
```

Renderer-only reload:

```javascript
await appWindow.reload({ waitUntil: "domcontentloaded" });
console.log("Reloaded Electron window");
```

Relaunch after main-process, preload, or startup changes:

```javascript
await electronApp.close().catch(() => {});
electronApp = undefined;
appWindow = undefined;

electronApp = await electronLauncher.launch({
  args: [ELECTRON_ENTRY],
});

appWindow = await electronApp.firstWindow();
console.log("Relaunched Electron window:", await appWindow.title());
```

## Code-Level Debugging

Use code inspection to answer concrete questions quickly:

- DOM state: `await page.content()`
- Visible controls: `await page.locator("button").allTextContents()`
- Browser logs: `page.on("console", (msg) => console.log(msg.type(), msg.text()))`
- Renderer state: `await page.evaluate(() => window.location.href)`
- Electron main-process diagnostics: `await electronApp.evaluate(...)`

Recommended pattern:

1. Inspect rendered state.
2. Form a concrete hypothesis.
3. Trigger the UI with normal input.
4. Re-check the visible outcome.
5. Only then decide whether the issue is logic, state, or presentation.

## Visual QA

Visual QA is mandatory when the user-visible result matters. Review the current state with screenshots and explicit checks for:

- viewport fit
- clipping and overflow
- broken alignment or spacing
- contrast and readability
- layering, overlays, and z-index issues
- motion or transition awkwardness
- Electron launched window size and initial layout

For Web screenshots intended for model review:

```javascript
await codex.emitImage({
  bytes: await page.screenshot({
    type: "jpeg",
    quality: 85,
    scale: "css",
  }),
  mimeType: "image/jpeg",
});
```

For Electron screenshots intended for model review:

```javascript
await codex.emitImage({
  bytes: await appWindow.screenshot({
    type: "jpeg",
    quality: 85,
  }),
  mimeType: "image/jpeg",
});
```

If coordinate-based follow-up actions depend on the screenshot, prefer CSS-scaled Web captures and Electron `BrowserWindow.capturePage(...)` normalization from the main process instead of guessing from device pixels.

## QA Inventory

Before signoff, write a short shared inventory that covers:

- user requirements
- implemented controls and visible behaviors
- states or mode changes each control can produce
- visible claims you expect to make in the final response
- at least two exploratory or off-happy-path checks

Every final claim should map to at least one functional check and one visual check when the claim is visible.

## Signoff Checklist

- The target runtime stayed in one persistent session during iteration.
- The main flow passed with normal user input.
- The visible result was confirmed, not inferred from internal state.
- Visual QA covered the relevant interface, not only the main happy path.
- Web or Electron viewport fit was checked in the actual startup state.
- The response can state which controls, states, and claims were exercised.
- Any intentional exclusions are called out explicitly.

## Cleanup

Only clean up when the task is actually finished:

```javascript
if (electronApp) {
  await electronApp.close().catch(() => {});
}

if (context) {
  await context.close().catch(() => {});
}

if (browser) {
  await browser.close().catch(() => {});
}

browser = undefined;
context = undefined;
page = undefined;
electronApp = undefined;
appWindow = undefined;

console.log("Playwright session closed");
```

## Common Failure Modes

- `Cannot find module 'playwright'`: rerun setup in the current workspace.
- `page.goto: net::ERR_CONNECTION_REFUSED`: the dev server is not running on the expected port.
- Electron hangs on launch: verify the local `electron` dependency and any renderer dev server.
- `Identifier has already been declared`: reuse the existing top-level bindings or wrap one-off code in `{ ... }`.
- Screenshots look correct but clicks miss the target: you probably mixed CSS pixels and device pixels.
