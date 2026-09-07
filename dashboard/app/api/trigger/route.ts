import { NextResponse } from "next/server";

const REPO = "Hamlet-Tamaz/naran-english-translation-pipeline";
const WORKFLOW = "process-video.yml";
// Parallel runs share one OpenAI API key and one git branch — they collide
// and fail. Enforce one run at a time, with minimum spacing between runs.
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

export async function POST(req: Request) {
  try {
    const { filename, robustness = "standard" } = await req.json();
    const token = process.env.GITHUB_TOKEN;
    if (!token) {
      return NextResponse.json({ message: "GITHUB_TOKEN not configured" }, { status: 500 });
    }
    if (!filename) {
      return NextResponse.json({ message: "No filename provided" }, { status: 400 });
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
        inputs: { video_filename: filename, robustness: robustness },
      }),
    });

    if (response.status === 204) {
      return NextResponse.json({ message: `Pipeline triggered [${robustness}] — one run at a time.` });
    }
    const data = await response.json().catch(() => ({}));
    return NextResponse.json({ message: data.message || "Trigger failed" }, { status: response.status });
  } catch (e: any) {
    return NextResponse.json({ message: `Error: ${e.message}` }, { status: 500 });
  }
}
