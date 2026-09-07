import { NextRequest, NextResponse } from "next/server";

// GET-triggerable pipeline runner — same logic as /api/trigger but callable
// via GET (for environments that can only fetch URLs).
// Usage: /api/run?key=<dashboard password>&filename=<file>&robustness=<level>
//
// SAFETY: refuses to dispatch while another run is active or was triggered
// less than 2 minutes ago. Parallel runs share one OpenAI API key and one
// git branch — they collide and fail (this happened on 2026-09-07 when 9
// dispatches fired within 20 seconds; only the first succeeded).

const REPO = "Hamlet-Tamaz/naran-english-translation-pipeline";
const WORKFLOW = "process-video.yml";
const MIN_SPACING_MS = 2 * 60 * 1000;

async function guardAgainstParallelRuns(token: string): Promise<string | null> {
  const headers = {
    Authorization: `token ${token}`,
    Accept: "application/vnd.github.v3+json",
  };
  const res = await fetch(
    `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=5`,
    { headers, cache: "no-store" }
  );
  if (!res.ok) return null; // can't check — fail open
  const runs = (await res.json()).workflow_runs || [];
  const active = runs.find((r: any) =>
    ["queued", "in_progress", "waiting", "requested", "pending"].includes(r.status)
  );
  if (active) {
    return `A pipeline run is already ${String(active.status).replace("_", " ")} — wait for it to finish before triggering another.`;
  }
  if (runs.length) {
    const lastStart = new Date(runs[0].created_at).getTime();
    const agoSec = Math.round((Date.now() - lastStart) / 1000);
    if (Date.now() - lastStart < MIN_SPACING_MS) {
      return `A run was triggered ${agoSec}s ago — to avoid collisions, wait at least 2 minutes between runs.`;
    }
  }
  return null;
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const key = searchParams.get("key");
  const filename = searchParams.get("filename");
  const robustness = searchParams.get("robustness") || "standard";

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

  const blocked = await guardAgainstParallelRuns(token);
  if (blocked) {
    return NextResponse.json({ message: blocked }, { status: 409 });
  }

  const url = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`;

  const response = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `token ${token}`,
      Accept: "application/vnd.github.v3+json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      ref: "main",
      inputs: { video_filename: filename, robustness },
    }),
  });

  if (response.status === 204) {
    return NextResponse.json({ message: `Pipeline triggered: ${filename} [${robustness}] — one run at a time.` });
  }
  const data = await response.json().catch(() => ({}));
  return NextResponse.json({ message: data.message || "Trigger failed" }, { status: response.status });
}
