#!/usr/bin/env node
import { chromium } from "@playwright/test";

const baseURL = process.env.CAIRN_BENCHMARK_URL ?? "http://127.0.0.1:8799";
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on("console", (message) => {
  if (message.type() === "error") errors.push(message.text());
});
page.on("pageerror", (error) => errors.push(error.message));

const startedSessions = performance.now();
await page.goto(`${baseURL}/sessions?preset=90d`, { waitUntil: "domcontentloaded" });
await page.locator("[data-trace-row]").first().waitFor();
const sessionsReadyMs = performance.now() - startedSessions;
const rowCount = await page.locator("[data-trace-row]").count();

const scrollMs = await page.evaluate(async () => {
  const started = performance.now();
  window.scrollTo({ top: document.body.scrollHeight });
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  window.scrollTo({ top: 0 });
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  return performance.now() - started;
});

const startedDetail = performance.now();
await page.goto(`${baseURL}/sessions/bench-trace-000000`, {
  waitUntil: "domcontentloaded",
});
const scrubber = page.getByLabel("Replay scrubber");
await scrubber.waitFor();
await page.locator("[data-span-id]").first().waitFor();
const detailReadyMs = performance.now() - startedDetail;
const initialVirtualRows = await page.locator("[data-span-id]").count();

const startedInteraction = performance.now();
await scrubber.fill("1250");
await page.locator("[data-span-id]").first().waitFor();
await page.evaluate(
  () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
);
const replayInteractionMs = performance.now() - startedInteraction;
const virtualRowsAfterReplay = await page.locator("[data-span-id]").count();

await browser.close();
const report = {
  base_url: baseURL,
  sessions_ready_ms: Number(sessionsReadyMs.toFixed(3)),
  session_page_rows: rowCount,
  session_scroll_ms: Number(scrollMs.toFixed(3)),
  wide_trace_ready_ms: Number(detailReadyMs.toFixed(3)),
  replay_interaction_ms: Number(replayInteractionMs.toFixed(3)),
  initial_virtual_rows: initialVirtualRows,
  virtual_rows_after_replay: virtualRowsAfterReplay,
  console_errors: errors,
};
process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
if (rowCount !== 50 || errors.length > 0) process.exitCode = 1;
