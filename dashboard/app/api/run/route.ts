import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 60;

// GET-triggerable pipeline runner — same logic as /api/trigger but callable
// via URL: /api/run?key=...&video=...&quality=...&confirm=true
//
// SAFETY MODEL:
// - BLOCKS (409) when the same video is already running at ANY quality
//   (parallel same-video runs share a version folder — one would lose its
//   results). Different videos run freely in parallel.
// - WARNS (requires confirm=true) when nothing changed since the last run
//   of the same video + quality (same pipeline code, same video file).
// - Otherwise dispatches immediately.

const REPO = "Hamlet-Tamaz/naran-english-translation-pipeline";
const WORKFLOW = "process-video.yml";
const STATE_PATH = ".run-state.json";
const ACTIVE_WINDOW_MS = 35 * 60 * 1000;
const ROBUSTNESS_LEVELS = ["draft", "standard", "high", "maximum"];

interface DispatchRecord {
  filename: string;
  robustness: string;
  dispatched_at: string;
  run_id?: number | null;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function gh(token: string, url: string, init: { method?: string; body?: string } = {}) {
  return fetch(url, {
    method: init.method || "GET",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "Content-Type": "application/json",
      "User-Agent": "naran-dashboard",
    },
    body: init.body,
  });
}

async function readState(token: string): Promise<{ dispatches: DispatchRecord[]; sha: string | null }> {
  const res = await gh(token, `https://api.github.com/repos/${REPO}/contents/${STATE_PATH}`);
  if (!res.ok) return { dispatches: [], sha: null };
  const data = await res.json();
  const parsed = JSON.parse(Buffer.from(data.content, "base64").toString("utf-8"));
  return { dispatches: parsed.dispatches || [], sha: data.sha };
}

async function writeState(token: string, dispatches: DispatchRecord[], sha: string | null) {
  const content = Buffer.from(JSON.stringify({ dispatches }, null, 2)).toString("base64");
  await gh(token, `https://api.github.com/repos/${REPO}/contents/${STATE_PATH}`, {
    method: "PUT",
    body: JSON.stringify({ message: "dashboard: record dispatch", content, ...(sha ? { sha } : {}) }),
  });
}

async function captureRunId(token: string, beforeRunId: number, dispatchedAt: string): Promise<number | null> {
  await sleep(4500);
  try {
    const res = await gh(token, `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=10`);
    if (!res.ok) return null;
    const data = await res.json();
    const since = new Date(dispatchedAt).getTime() - 10000;
    const runs = (data.workflow_runs || []).filter(
      (r: any) => r.id > beforeRunId && new Date(r.created_at).getTime() >= since,
    );
    if (runs.length === 1) return runs[0].id;
    return null;
  } catch {
    return null;
  }
}

async function runStatus(token: string, runId: number): Promise<{ status: string; conclusion: string | null } | null> {
  const res = await gh(token, `https://api.github.com/repos/${REPO}/actions/runs/${runId}`);
  if (!res.ok) return null;
  const r = await res.json();
  return { status: r.status, conclusion: r.conclusion };
}

async function completionCommitSince(token: string, filename: string, robustness: string, sinceISO: string): Promise<boolean> {
  const res = await gh(token, `https://api.github.com/repos/${REPO}/commits?since=${encodeURIComponent(sinceISO)}&per_page=30`);
  if (!res.ok) return false;
  const commits = await res.json();
  const needle = `pipeline: process ${filename} [${robustness}]`;
  return commits.some((c: any) => (c.commit?.message || "").startsWith(needle));
}

// Is this video already running at ANY quality? Parallel runs of the same
// video both compute the same next version number and write to the same
// version folder + versions.json — one run's results would be lost at the
// final git rebase. (Different videos are safe: disjoint folders, and their
// queue.json edits touch different lines and merge cleanly.)
async function findActiveDuplicate(token: string, dispatches: DispatchRecord[], filename: string): Promise<DispatchRecord | null> {
  const now = Date.now();
  for (let i = dispatches.length - 1; i >= 0; i--) {
    const d = dispatches[i];
    if (d.filename !== filename) continue;
    const age = now - new Date(d.dispatched_at).getTime();
    if (age > ACTIVE_WINDOW_MS) continue; // stale — assume dead
    if (d.run_id) {
      const rs = await runStatus(token, d.run_id);
      if (rs) {
        if (["queued", "in_progress", "waiting", "requested", "pending"].includes(rs.status)) return d;
        continue; // completed/failed/cancelled — not active
      }
    }
    // Fallback without run status: a completion commit means it finished
    if (await completionCommitSince(token, filename, d.robustness, d.dispatched_at)) continue;
    return d;
  }
  return null;
}

async function lastRunForCombo(token: string, dispatches: DispatchRecord[], filename: string, robustness: string): Promise<{ at: string; record: DispatchRecord | null } | null> {
  const ours = dispatches.filter((d) => d.filename === filename && d.robustness === robustness);
  let at: string | null = ours.length ? ours[ours.length - 1].dispatched_at : null;
  const record = ours.length ? ours[ours.length - 1] : null;
  const res = await gh(token, `https://api.github.com/repos/${REPO}/commits?per_page=50`);
  if (res.ok) {
    const commits = await res.json();
    const needle = `pipeline: process ${filename} [${robustness}]`;
    const match = commits.find((c: any) => (c.commit?.message || "").startsWith(needle));
    if (match) {
      const d = match.commit.committer.date;
      if (!at || new Date(d) > new Date(at)) at = d;
    }
  }
  return at ? { at, record } : null;
}

async function changedSince(token: string, path: string, sinceISO: string): Promise<boolean> {
  const res = await gh(token, `https://api.github.com/repos/${REPO}/commits?path=${encodeURIComponent(path)}&since=${encodeURIComponent(sinceISO)}&per_page=1`);
  if (!res.ok) return true; // can't check → assume changed (don't nag)
  const commits = await res.json();
  return commits.length > 0;
}

export async function GET(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const key = url.searchParams.get("key") || "";
    const filename = (url.searchParams.get("video") || "").trim();
    const robustness = (url.searchParams.get("quality") || "standard").trim().toLowerCase();
    const confirm = url.searchParams.get("confirm") === "true";

    if (!process.env.RUN_TRIGGER_KEY || key !== process.env.RUN_TRIGGER_KEY) {
      return NextResponse.json({ message: "Unauthorized" }, { status: 401 });
    }
    const token = process.env.GITHUB_TOKEN;
    if (!token) {
      return NextResponse.json({ message: "GITHUB_TOKEN not configured" }, { status: 500 });
    }

    const { dispatches, sha } = await readState(token);

    // BLOCK when the same video is already running at ANY quality.
    // Different videos may run in parallel.
    const dup = await findActiveDuplicate(token, dispatches, filename);
    if (dup) {
      return NextResponse.json(
        { message: `A run for ${filename} [${dup.robustness}] is already in progress. Parallel runs of the same video write to the same version folder and one would lose its results — please wait for it to finish. Different videos can run in parallel.` },
        { status: 409 }
      );
    }

    if (!confirm) {
      const last = await lastRunForCombo(token, dispatches, filename, robustness);
      if (last) {
        let lastFailed = false;
        if (last.record?.run_id) {
          const rs = await runStatus(token, last.record.run_id);
          if (rs && rs.status === "completed" && rs.conclusion !== "success") lastFailed = true;
        }
        if (!lastFailed) {
          const checks = await Promise.all([
            changedSince(token, "pipeline", last.at),
            changedSince(token, ".github/workflows", last.at),
            changedSince(token, `incoming/${filename}`, last.at),
          ]);
          if (!checks.some(Boolean)) {
            return NextResponse.json(
              {
                requires_confirmation: true,
                warning: `Nothing has changed since the last ${filename} [${robustness}] run (${last.at.slice(0, 16).replace("T", " ")} UTC): same pipeline code, same video file, same quality. Re-processing will produce the same result and burn a full run. Run it anyway? Append &confirm=true to proceed.`,
              },
              { status: 200 },
            );
          }
        }
      }
    }

    if (!ROBUSTNESS_LEVELS.includes(robustness)) {
      return NextResponse.json({ message: "Invalid robustness level" }, { status: 400 });
    }
    if (!filename) return NextResponse.json({ message: "No video provided" }, { status: 400 });

    let beforeRunId = 0;
    try {
      const res = await gh(token, `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=1`);
      if (res.ok) {
        const data = await res.json();
        beforeRunId = data.workflow_runs?.[0]?.id || 0;
      }
    } catch { /* non-fatal */ }

    const dispatchedAt = new Date().toISOString();
    const dispatchRes = await gh(
      token,
      `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
      {
        method: "POST",
        body: JSON.stringify({
          ref: "main",
          inputs: { video_filename: filename, robustness },
        }),
      },
    );

    if (!dispatchRes.ok) {
      const text = await dispatchRes.text();
      return NextResponse.json(
        { message: "Failed to trigger pipeline", details: text },
        { status: dispatchRes.status },
      );
    }

    const run_id = await captureRunId(token, beforeRunId, dispatchedAt);
    dispatches.push({ filename, robustness, dispatched_at: dispatchedAt, run_id });
    await writeState(token, dispatches.slice(-200), sha);

    return NextResponse.json({
      message: `Pipeline triggered for ${filename} [${robustness}]`,
      run_id,
    });
  } catch (err) {
    return NextResponse.json(
      { message: "Failed to trigger pipeline", details: String(err) },
      { status: 500 },
    );
  }
}
