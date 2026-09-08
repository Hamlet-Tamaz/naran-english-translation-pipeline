import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 60;

// Saves speaker-attribution corrections for a video and updates the
// persistent voice bank. Called by the dashboard SpeakerEditor.
//
// POST body:
//   key          dashboard password (same guard as /api/run)
//   video        video id WITHOUT .mp4 (e.g. "naran-hangai-smaller")
//   rules        full replacement rule list for the video:
//                [{ start, end, speaker, note?, created_at?, text_override? }]
//   bank_updates [{ speaker, vectors: number[][] }] — cluster embeddings the
//                user confirmed for that speaker; merged into their profile
//   bank_resets  [speaker] — delete these voice profiles
//
// Writes (via GitHub contents API):
//   processed/<video>/corrections.json   — per-video attribution rules
//   speaker-bank/profiles.json           — persistent cross-video voices

const REPO = "Hamlet-Tamaz/naran-english-translation-pipeline";
const BANK_PATH = "speaker-bank/profiles.json";

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

async function readRepoFile(token: string, path: string): Promise<{ data: any | null; sha: string | null }> {
  const res = await gh(token, `https://api.github.com/repos/${REPO}/contents/${path}?ref=main`);
  if (!res.ok) return { data: null, sha: null };
  const file = await res.json();
  try {
    return { data: JSON.parse(Buffer.from(file.content, "base64").toString("utf-8")), sha: file.sha };
  } catch {
    return { data: null, sha: file.sha };
  }
}

async function putRepoFile(token: string, path: string, obj: any, sha: string | null, message: string): Promise<boolean> {
  const body: Record<string, any> = {
    message,
    content: Buffer.from(JSON.stringify(obj, null, 2)).toString("base64"),
    branch: "main",
  };
  if (sha) body.sha = sha;
  const res = await gh(token, `https://api.github.com/repos/${REPO}/contents/${path}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
  return res.ok;
}

function normVec(v: number[]): number[] {
  const n = Math.sqrt(v.reduce((s, x) => s + x * x, 0)) || 1;
  return v.map((x) => x / n);
}

// Running weighted average, re-normalized — mirrors pipeline/speaker_bank.py
function mergeProfile(prof: any | undefined, vectors: number[][], video: string, now: string) {
  const pool: number[][] = [];
  if (prof?.embedding?.length) {
    const reps = Math.max(prof.samples || 1, 1);
    for (let i = 0; i < reps; i++) pool.push(prof.embedding);
  }
  pool.push(...vectors);
  const dims = pool[0]?.length || 0;
  const usable = pool.filter((v) => v.length === dims);
  if (!dims || usable.length === 0) return null;
  const acc = new Array(dims).fill(0);
  for (const v of usable) for (let i = 0; i < dims; i++) acc[i] += v[i];
  const embedding = normVec(acc.map((x) => x / usable.length)).map((x) => Math.round(x * 1e6) / 1e6);
  const videos = Array.from(new Set([...(prof?.videos || []), video])).sort();
  return {
    embedding,
    samples: (prof?.samples || 0) + vectors.length,
    videos,
    updated_at: now,
  };
}

function cleanVector(v: any): number[] | null {
  if (!Array.isArray(v) || v.length < 32 || v.length > 1024) return null;
  if (!v.every((x) => typeof x === "number" && Number.isFinite(x))) return null;
  return v as number[];
}

export async function POST(req: Request) {
  try {
    const body = await req.json();

    if (body.key !== "translathor888") {
      return NextResponse.json({ message: "Invalid key" }, { status: 401 });
    }
    const token = process.env.GITHUB_TOKEN;
    if (!token) {
      return NextResponse.json({ message: "GITHUB_TOKEN not configured" }, { status: 500 });
    }

    const video = String(body.video || "").trim();
    if (!/^[\w][\w.-]*$/.test(video)) {
      return NextResponse.json({ message: "Invalid video id" }, { status: 400 });
    }

    const now = new Date().toISOString();

    // ---- validate rules (full replacement list; omit field to leave
    //      an existing corrections.json untouched, e.g. profile resets) ----
    const hasRules = Array.isArray(body.rules);
    const rawRules = hasRules ? body.rules : [];
    if (rawRules.length > 500) {
      return NextResponse.json({ message: "Too many rules (max 500)" }, { status: 400 });
    }
    const rules = rawRules
      .filter((r: any) =>
        r && Number.isFinite(r.start) && Number.isFinite(r.end) &&
        r.end > r.start && r.start >= 0 &&
        typeof r.speaker === "string" && r.speaker.trim().length > 0 && r.speaker.length <= 60)
      .map((r: any, i: number) => ({
        id: typeof r.id === "string" && r.id ? r.id : `r${i + 1}`,
        start: Math.round(r.start * 100) / 100,
        end: Math.round(r.end * 100) / 100,
        speaker: r.speaker.trim(),
        ...(typeof r.note === "string" && r.note ? { note: r.note.slice(0, 200) } : {}),
        ...(typeof r.text_override === "string" && r.text_override.trim() ? { text_override: r.text_override.slice(0, 4000) } : {}),
        created_at: typeof r.created_at === "string" && r.created_at ? r.created_at : now,
        updated_at: now,
      }))
      .sort((a: any, b: any) => a.start - b.start);

    // ---- 1) write corrections.json (only when rules were sent) ----
    if (hasRules) {
      const correctionsPath = `processed/${video}/corrections.json`;
      let saved = false;
      for (let attempt = 0; attempt < 2 && !saved; attempt++) {
        const cur = await readRepoFile(token, correctionsPath);
        saved = await putRepoFile(
          token,
          correctionsPath,
          { video, updated_at: now, rules },
          cur.sha,
          `dashboard: attribution rules for ${video} (${rules.length} rules)`,
        );
      }
      if (!saved) {
        return NextResponse.json({ message: "Failed to save corrections.json (git conflict, try again)" }, { status: 502 });
      }
    }

    // ---- 2) voice bank updates / resets ----
    const resets: string[] = (Array.isArray(body.bank_resets) ? body.bank_resets : [])
      .filter((s: any) => typeof s === "string" && s.trim()).map((s: string) => s.trim()).slice(0, 50);
    const updates = (Array.isArray(body.bank_updates) ? body.bank_updates : [])
      .map((u: any) => ({
        speaker: typeof u?.speaker === "string" ? u.speaker.trim() : "",
        vectors: (Array.isArray(u?.vectors) ? u.vectors : []).map(cleanVector).filter(Boolean).slice(0, 20) as number[][],
      }))
      .filter((u: any) => u.speaker && u.vectors.length > 0)
      .slice(0, 50);

    let profilesSummary: Record<string, any> = {};
    if (resets.length > 0 || updates.length > 0) {
      let bankSaved = false;
      for (let attempt = 0; attempt < 2 && !bankSaved; attempt++) {
        const cur = await readRepoFile(token, BANK_PATH);
        const bank = cur.data && cur.data.profiles && typeof cur.data.profiles === "object"
          ? cur.data
          : { profiles: {} };
        for (const name of resets) delete bank.profiles[name];
        for (const u of updates) {
          const merged = mergeProfile(bank.profiles[u.speaker], u.vectors, video, now);
          if (merged) bank.profiles[u.speaker] = merged;
        }
        const touched = [...updates.map((u: any) => u.speaker), ...resets.map((r) => `${r} (reset)`)].join(", ");
        bankSaved = await putRepoFile(token, BANK_PATH, bank, cur.sha, `dashboard: voice bank update (${touched})`);
        if (bankSaved) {
          profilesSummary = Object.fromEntries(
            Object.entries(bank.profiles).map(([n, p]: [string, any]) => [
              n,
              { samples: p.samples, videos: p.videos?.length || 0, updated_at: p.updated_at },
            ]),
          );
        }
      }
      if (!bankSaved) {
        return NextResponse.json({ message: "Rules saved, but voice bank update failed (git conflict, save again)" }, { status: 502 });
      }
    }

    return NextResponse.json({
      message:
        (hasRules ? `Saved ${rules.length} attribution rule(s) for ${video}` : `No rule changes for ${video}`) +
        (updates.length ? `; voice bank updated for ${updates.map((u: any) => u.speaker).join(", ")}` : "") +
        (resets.length ? `; reset: ${resets.join(", ")}` : ""),
      profiles: profilesSummary,
    });
  } catch (e: any) {
    return NextResponse.json({ message: `Error: ${e.message}` }, { status: 500 });
  }
}
