import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 60;

// GET-triggerable pipeline runner — same logic as /api/trigger but callable
// via GET (for environments that can only fetch URLs).
// Usage: /api/run?key=<dashboard password>&filename=<file>&robustness=<level>
//
// SAFETY MODEL:
// - BLOCKS (409) only when the exact same video + quality is already running.
//   Different videos, or the same video at a different quality, run freely
//   in parallel.
// - WARNS (requires_confirmation) when reprocessing a combo whose inputs have
//   not changed since its last run (same pipeline code, same video file,
//   same quality). Re-call with &confirm=true to proceed anyway.

const REPO = "Hamlet-Tamaz/naran-english-translation-pipeline";
const WORKFLOW = "process-video.yml";
const STATE_PATH = ".run-state.json";
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

async function captureRunId(token: string, beforeRunId: number, dispatchedAt: string): Promise<number | null> {
  await sleep(4500);
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

async function findActiveDuplicate(token: string, dispatches: DispatchRecord[], filename: string, robustness: string): Promise<DispatchRecord | null> {
  const now = Date.now();
  for (let i = dispatches.length - 1; i >= 0; i--) {
    const d = dispatches[i];
    if (d.filename !== filename || d.robustness !== robustness) continue;
    const age = now - new Date(d.dispatched_at).getTime();
    if (age > ACTIVE_WINDOW_MS) continue;
    if (d.run_id) {
      const rs = await runStatus(token, d.run_id);
      if (rs) {
        if (["queued", "in_progress", "waiting", "requested", "pending"].includes(rs.status)) return d;
        continue;
      }
    }
    if (await completionCommitSince(token, filename, robustness, d.dispatched_at)) continue;
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
  if (!res.ok) return true;
  return (await res.json()).length > 0;
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const key = searchParams.get("key");
  const filename = searchParams.get("filename");
  const robustness = searchParams.get("robustness") || "standard";
  const confirm = searchParams.get("confirm") === "true";

  if (key !== "translathor888") {
    return NextResponse.json({ message: "Invalid key" }, { status: 401 });
  }
  if (!filename) {
    return NextResponse.json({ message: "No filename provided" }, { status: 400 });
  }

  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    return NextResponse.json({ message: "GITHUB_TOKEN not configured" }, { status: 500 });
  }

  const { dispatches, sha } = await readState(token);

  const dup = await findActiveDuplicate(token, dispatches, filename, robustness);
  if (dup) {
    return NextResponse.json(
      { message: `This exact run — ${filename} [${robustness}] — is already in progress. Wait for it to finish, or choose a different quality to run alongside it.` },
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
        const [codeChanged, workflowChanged, videoChanged] = await Promise.all([
          changedSince(token, "pipeline", last.at),
          changedSince(token, ".github/workflows", last.at),
          changedSince(token, `incoming/${filename}`, last.at),
        ]);
        if (!codeChanged && !workflowChanged && !videoChanged) {
          return NextResponse.json({
            requires_confirmation: true,
            warning: `Nothing has changed since the last [${robustness}] run of ${filename} — same pipeline code, same video file, same quality. The result will very likely be identical. To run anyway, re-call this URL with &confirm=true`,
          });
        }
      }
    }
  }

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
    try {
      const runId = await captureRunId(token, beforeRunId, dispatchedAt);
      const updated = [...dispatches, { filename, robustness, dispatched_at: dispatchedAt, run_id: runId }].slice(-200);
      await writeState(token, updated, sha);
    } catch {}
    return NextResponse.json({ message: `Pipeline triggered: ${filename} [${robustness}]` });
  }
  const data = await response.json().catch(() => ({}));
  return NextResponse.json({ message: data.message || "Trigger failed" }, { status: response.status });
}
