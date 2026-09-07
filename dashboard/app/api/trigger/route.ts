import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 60;

const REPO = "Hamlet-Tamaz/naran-english-translation-pipeline";
const WORKFLOW = "process-video.yml";
const STATE_PATH = ".run-state.json";
// A dispatch without a known run status is assumed "maybe active" for up to
// 35 minutes (the workflow itself times out at 30).
const ACTIVE_WINDOW_MS = 35 * 60 * 1000;

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
    body: init.body,
    cache: "no-store",
    headers: {
      Authorization: `token ${token}`,
      Accept: "application/vnd.github.v3+json",
      "Content-Type": "application/json",
    },
  });
}

async function readState(token: string): Promise<{ dispatches: DispatchRecord[]; sha: string | null }> {
  const res = await gh(token, `https://api.github.com/repos/${REPO}/contents/${STATE_PATH}?ref=main`);
  if (!res.ok) return { dispatches: [], sha: null };
  const data = await res.json();
  try {
    const parsed = JSON.parse(Buffer.from(data.content, "base64").toString("utf-8"));
    return { dispatches: parsed.dispatches || [], sha: data.sha };
  } catch {
    return { dispatches: [], sha: data.sha };
  }
}

async function writeState(token: string, dispatches: DispatchRecord[], sha: string | null) {
  const body: Record<string, any> = {
    message: "dashboard: record pipeline dispatch",
    content: Buffer.from(JSON.stringify({ dispatches }, null, 2)).toString("base64"),
    branch: "main",
  };
  if (sha) body.sha = sha;
  await gh(token, `https://api.github.com/repos/${REPO}/contents/${STATE_PATH}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

// Find the run created by a dispatch: any run id greater than the newest one
// that existed just before we dispatched. Returns null if ambiguous.
async function captureRunId(token: string, beforeRunId: number, dispatchedAt: string): Promise<number | null> {
  await sleep(4500); // GitHub takes a few seconds to register the run
  const res = await gh(token, `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=10`);
  if (!res.ok) return null;
  const runs = (await res.json()).workflow_runs || [];
  const since = new Date(new Date(dispatchedAt).getTime() - 20000);
  const candidates = runs.filter(
    (r: any) => r.id > beforeRunId && new Date(r.created_at) >= since
  );
  return candidates.length === 1 ? candidates[0].id : null;
}

async function runStatus(token: string, runId: number): Promise<{ status: string; conclusion: string | null } | null> {
  const res = await gh(token, `https://api.github.com/repos/${REPO}/actions/runs/${runId}`);
  if (!res.ok) return null;
  const run = await res.json();
  return { status: run.status, conclusion: run.conclusion };
}

async function completionCommitSince(token: string, filename: string, robustness: string, sinceISO: string): Promise<boolean> {
  const res = await gh(token, `https://api.github.com/repos/${REPO}/commits?per_page=50&since=${encodeURIComponent(sinceISO)}`);
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

// When did this combo last run? (state records + completion commits fallback)
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
  return (await res.json()).length > 0;
}

export async function POST(req: Request) {
  try {
    const { filename, robustness = "standard", confirm = false } = await req.json();
    const token = process.env.GITHUB_TOKEN;
    if (!token) return NextResponse.json({ message: "GITHUB_TOKEN not configured" }, { status: 500 });
    if (!filename) return NextResponse.json({ message: "No filename provided" }, { status: 400 });

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

    // WARN (not block) when reprocessing with no changes since the last run
    // of this combo: same pipeline code, same video file, same quality.
    // If the previous attempt failed, allow a retry without nagging.
    if (!confirm) {
      const last = await lastRunForCombo(token, dispatches, filename, robustness);
      if (last) {
        let lastFailed = false;
        if (last.record?.run_id) {
          const rs = await runStatus(token, last.record.run_id);
          if (rs && rs.status === "completed" && rs.conclusion !== "success") lastFailed = true;
        }
        if (!lastFailed) {
          const [codeChanged, workflowChanged, videoChanged] = await Promise.all([
            changedSince(token, "pipeline", last.at),
            changedSince(token, ".github/workflows", last.at),
            changedSince(token, `incoming/${filename}`, last.at),
          ]);
          if (!codeChanged && !workflowChanged && !videoChanged) {
            return NextResponse.json({
              requires_confirmation: true,
              warning: `Nothing has changed since the last [${robustness}] run of ${filename} — same pipeline code, same video file, same quality. The result will very likely be identical. Reprocess anyway?`,
            });
          }
        }
      }
    }

    // Snapshot the newest run id so we can identify our run afterwards
    let beforeRunId = 0;
    const preRes = await gh(token, `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=1`);
    if (preRes.ok) {
      const preRuns = (await preRes.json()).workflow_runs || [];
      if (preRuns.length) beforeRunId = preRuns[0].id;
    }

    const dispatchedAt = new Date().toISOString();
    const response = await gh(token, `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`, {
      method: "POST",
      body: JSON.stringify({ ref: "main", inputs: { video_filename: filename, robustness } }),
    });

    if (response.status === 204) {
      // Best-effort: record the dispatch (with run id if we can capture it)
      try {
        const runId = await captureRunId(token, beforeRunId, dispatchedAt);
        const updated = [...dispatches, { filename, robustness, dispatched_at: dispatchedAt, run_id: runId }].slice(-200);
        await writeState(token, updated, sha);
      } catch {}
      return NextResponse.json({ message: `Pipeline triggered [${robustness}]` });
    }
    const data = await response.json().catch(() => ({}));
    return NextResponse.json({ message: data.message || "Trigger failed" }, { status: response.status });
  } catch (e: any) {
    return NextResponse.json({ message: `Error: ${e.message}` }, { status: 500 });
  }
}
