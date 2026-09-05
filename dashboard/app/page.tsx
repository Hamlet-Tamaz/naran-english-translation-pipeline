"use client";
import { useState, useEffect, useCallback, useRef } from "react";

interface QueueVideo {
  filename: string;
  status: string;
  source_url?: string;
  uploaded_at: string | null;
  processed_at: string | null;
}

interface EnvStatus {
  ready: boolean;
  github_ready: boolean;
  r2_ready: boolean;
  checks: Record<string, boolean>;
}

export default function Dashboard() {
  const [videos, setVideos] = useState<QueueVideo[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [envStatus, setEnvStatus] = useState<EnvStatus | null>(null);
  const [checkingEnv, setCheckingEnv] = useState(true);
  const [previewVideo, setPreviewVideo] = useState<string | null>(null);
  const [previewCaption, setPreviewCaption] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    checkEnv();
    fetchQueue();
    const interval = setInterval(fetchQueue, 10000);
    return () => clearInterval(interval);
  }, []);

  async function checkEnv() {
    try {
      const res = await fetch("/api/env-check");
      const data = await res.json();
      setEnvStatus(data);
    } catch (e) {
      setEnvStatus({ ready: false, github_ready: false, r2_ready: false, checks: {} });
    } finally {
      setCheckingEnv(false);
    }
  }

  async function fetchQueue() {
    try {
      const res = await fetch("https://raw.githubusercontent.com/Hamlet-Tamaz/naran-english-translation-pipeline/main/queue.json");
      const data = await res.json();
      setVideos(data.videos || []);
    } catch (e) {
      console.error("Failed to fetch queue", e);
    }
  }

  async function reprocessVideo(filename: string) {
    setLoading(true);
    setMessage(`Re-processing ${filename}...`);
    try {
      const res = await fetch("/api/reprocess", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename }),
      });
      const data = await res.json();
      setMessage(data.message || "Re-processing started!");
    } catch (e) {
      setMessage("Error re-processing video. Check console.");
    }
    setLoading(false);
  }

  async function triggerPipeline(filename: string) {
    setLoading(true);
    setMessage("Triggering pipeline...");
    try {
      const res = await fetch("/api/trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename }),
      });
      const data = await res.json();
      setMessage(data.message || "Pipeline triggered!");
    } catch (e) {
      setMessage("Error triggering pipeline. Check console.");
    }
    setLoading(false);
  }

  async function triggerScan() {
    setLoading(true);
    setMessage("Triggering manual scan...");
    try {
      const res = await fetch("/api/scan", { method: "POST" });
      const data = await res.json();
      setMessage(data.message || "Scan triggered!");
    } catch (e) {
      setMessage("Error triggering scan.");
    }
    setLoading(false);
  }

  async function uploadFile(file: File) {
    setUploadProgress(0);
    setMessage(`Uploading ${file.name}...`);
    if (envStatus?.r2_ready) {
      await uploadToR2(file);
    } else {
      await uploadDirect(file);
    }
  }

  async function uploadDirect(file: File) {
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch("/api/upload", { method: "POST", body: formData });
      const data = await res.json();
      if (res.ok) {
        setMessage(`Uploaded ${file.name}! Appears in Pending.`);
        setUploadProgress(100);
        fetchQueue();
      } else {
        setMessage(`Error: ${data.message || "Upload failed"}`);
        setUploadProgress(0);
      }
    } catch (e: any) {
      setMessage(`Error: ${e.message}`);
      setUploadProgress(0);
    }
  }

  async function uploadToR2(file: File) {
    try {
      const presignRes = await fetch("/api/upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: file.name, contentType: file.type }),
      });
      if (!presignRes.ok) {
        const err = await presignRes.json();
        setMessage(`Error: ${err.message || "Failed to get upload URL"}`);
        setUploadProgress(0);
        return;
      }
      const { presignedUrl, objectKey, publicUrl } = await presignRes.json();
      setMessage(`Uploading ${file.name} to cloud storage...`);
      const xhr = new XMLHttpRequest();
      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) setUploadProgress(Math.round((e.loaded / e.total) * 100));
      });
      await new Promise<void>((resolve, reject) => {
        xhr.addEventListener("load", () => {
          if (xhr.status >= 200 && xhr.status < 300) resolve();
          else reject(new Error(`Upload failed: ${xhr.status}`));
        });
        xhr.addEventListener("error", () => reject(new Error("Network error")));
        xhr.open("PUT", presignedUrl);
        xhr.setRequestHeader("Content-Type", file.type);
        xhr.send(file);
      });
      setMessage("Finalizing...");
      const confirmRes = await fetch("/api/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: file.name, publicUrl, objectKey }),
      });
      if (confirmRes.ok) {
        setMessage(`Uploaded ${file.name}! Appears in Pending.`);
        setUploadProgress(100);
        fetchQueue();
      } else {
        const err = await confirmRes.json();
        setMessage(`Error: ${err.message || "Confirm failed"}`);
        setUploadProgress(0);
      }
    } catch (e: any) {
      setMessage(`Error: ${e.message}`);
      setUploadProgress(0);
    }
  }

  async function openPreview(filename: string) {
    const videoId = filename.replace(".mp4", "");
    const videoUrl = `https://raw.githubusercontent.com/Hamlet-Tamaz/naran-english-translation-pipeline/main/processed/${videoId}/final.mp4`;

    // Fetch caption
    try {
      const res = await fetch(`https://raw.githubusercontent.com/Hamlet-Tamaz/naran-english-translation-pipeline/main/processed/${videoId}/caption.txt`);
      const caption = await res.text();
      setPreviewCaption(caption);
    } catch (e) {
      setPreviewCaption("");
    }

    setPreviewVideo(videoUrl);
  }

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith("video/")) uploadFile(file);
    else setMessage("Error: Please drop a video file (MP4, MOV, etc.)");
  }, [envStatus]);

  const onDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); }, []);
  const onDragLeave = useCallback((e: React.DragEvent) => { e.preventDefault(); setIsDragging(false); }, []);

  const onFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) uploadFile(file);
  };

  const pending = videos.filter(v => v.status === "pending_approval");
  const completed = videos.filter(v => v.status === "completed");
  const processing = videos.filter(v => v.status === "processing");

  const githubReady = envStatus?.github_ready ?? false;
  const kimiReady = envStatus?.kimi_ready ?? false;
  const openaiReady = envStatus?.openai_ready ?? false;
  const r2Ready = envStatus?.r2_ready ?? false;
  const canUpload = githubReady;

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "32px 16px" }}>
      <header style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: 28, fontWeight: 600, margin: 0, color: "#fafafa" }}>Naran Pipeline</h1>
        <p style={{ margin: "8px 0 0", color: "#a1a1aa", fontSize: 14 }}>Armenian content → English translation, voiceover & subtitles</p>
      </header>

      {!checkingEnv && (
        <div style={{ padding: "14px 18px", borderRadius: 10, marginBottom: 24, border: "1px solid #27272a", background: "rgba(255,255,255,0.02)" }}>
          <div style={{ fontSize: 13, fontWeight: 500, color: "#d4d4d8", marginBottom: 10 }}>System Status</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <StatusRow label="GitHub API" ready={githubReady} />
            <StatusRow label="Cloud Storage (R2)" ready={r2Ready} optional />
          </div>
          {!githubReady && (
            <div style={{ marginTop: 10, fontSize: 12, color: "#f87171" }}>
              Add GITHUB_TOKEN to Vercel Environment Variables and redeploy.
            </div>
          )}
        </div>
      )}

      {message && (
        <div style={{ padding: "12px 16px", borderRadius: 8, marginBottom: 20, background: message.includes("Error") ? "rgba(239,68,68,0.15)" : "rgba(34,197,94,0.15)", color: message.includes("Error") ? "#fca5a5" : "#86efac", fontSize: 14 }}>
          {message}
        </div>
      )}

      <div
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={() => canUpload && fileInputRef.current?.click()}
        style={{ padding: "40px 24px", borderRadius: 12, border: `2px dashed ${isDragging ? "#3b82f6" : canUpload ? "#3f3f46" : "#27272a"}`, background: isDragging ? "rgba(59,130,246,0.08)" : "rgba(255,255,255,0.02)", textAlign: "center", cursor: canUpload ? "pointer" : "not-allowed", transition: "all 0.2s ease", marginBottom: 32, opacity: canUpload ? 1 : 0.5 }}
      >
        <input ref={fileInputRef} type="file" accept="video/*" onChange={onFileSelect} style={{ display: "none" }} disabled={!canUpload} />
        <div style={{ fontSize: 32, marginBottom: 8 }}>📤</div>
        <div style={{ fontSize: 15, fontWeight: 500, color: canUpload ? "#d4d4d8" : "#71717a" }}>
          {canUpload ? (r2Ready ? "Drop a video here, or click to browse" : "Drop a video here (max ~4.5MB)") : "Upload disabled — complete setup first"}
        </div>
        <div style={{ fontSize: 12, color: "#71717a", marginTop: 6 }}>
          {r2Ready ? "Any size via Cloudflare R2" : "MP4, MOV, AVI — enable R2 for larger files"}
        </div>
        {uploadProgress > 0 && uploadProgress < 100 && (
          <div style={{ marginTop: 16 }}>
            <div style={{ height: 4, borderRadius: 2, background: "#27272a", overflow: "hidden" }}>
              <div style={{ height: "100%", width: `${uploadProgress}%`, background: "#3b82f6", borderRadius: 2, transition: "width 0.3s ease" }} />
            </div>
            <div style={{ fontSize: 11, color: "#71717a", marginTop: 4 }}>Uploading... {uploadProgress}%</div>
          </div>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 32 }}>
        <StatCard label="Pending" value={pending.length} color="#f59e0b" />
        <StatCard label="Processing" value={processing.length} color="#3b82f6" />
        <StatCard label="Completed" value={completed.length} color="#22c55e" />
      </div>

      <div style={{ display: "flex", gap: 12, marginBottom: 24 }}>
        <button onClick={triggerScan} disabled={loading || !githubReady} style={{ padding: "10px 20px", borderRadius: 8, border: "1px solid #3f3f46", background: "transparent", color: githubReady ? "#d4d4d8" : "#52525b", fontSize: 13, fontWeight: 500, cursor: (loading || !githubReady) ? "not-allowed" : "pointer" }}>🔍 Scan Now</button>
        <button onClick={fetchQueue} disabled={loading} style={{ padding: "10px 20px", borderRadius: 8, border: "1px solid #3f3f46", background: "transparent", color: "#d4d4d8", fontSize: 13, fontWeight: 500, cursor: loading ? "not-allowed" : "pointer" }}>🔄 Refresh</button>
      </div>

      <Section title="Pending Approval" count={pending.length}>
        {pending.length === 0 ? (
          <EmptyState text="No videos waiting. Upload one above or click Scan Now." />
        ) : (
          pending.map(v => (
            <VideoRow key={v.filename} video={v}>
              <button onClick={() => triggerPipeline(v.filename)} disabled={loading} style={{ padding: "8px 16px", borderRadius: 6, border: "none", background: "#fafafa", color: "#18181b", fontSize: 13, fontWeight: 500, cursor: loading ? "not-allowed" : "pointer", opacity: loading ? 0.6 : 1 }}>
                {loading ? "Starting..." : "Process"}
              </button>
            </VideoRow>
          ))
        )}
      </Section>

      <Section title="Completed" count={completed.length}>
        {completed.length === 0 ? (
          <EmptyState text="No processed videos yet." />
        ) : (
          completed.map(v => (
            <VideoRow key={v.filename} video={v}>
              <div style={{ display: "flex", gap: 8 }}>
                <button onClick={() => openPreview(v.filename)} style={{ padding: "8px 16px", borderRadius: 6, border: "1px solid #3b82f6", background: "transparent", color: "#3b82f6", fontSize: 13, fontWeight: 500, cursor: "pointer" }}>
                  ▶ Watch
                </button>
                <button onClick={() => reprocessVideo(v.filename)} disabled={loading} style={{ padding: "8px 16px", borderRadius: 6, border: "1px solid #f59e0b", background: "transparent", color: "#f59e0b", fontSize: 13, fontWeight: 500, cursor: loading ? "not-allowed" : "pointer", opacity: loading ? 0.6 : 1 }}>
                  🔄 Re-process
                </button>
                <a
                  href={`https://github.com/Hamlet-Tamaz/naran-english-translation-pipeline/tree/main/processed/${v.filename.replace(".mp4", "")}`}
                  target="_blank"
                  rel="noopener"
                  style={{ padding: "8px 16px", borderRadius: 6, border: "1px solid #3f3f46", background: "transparent", color: "#a1a1aa", fontSize: 13, textDecoration: "none", display: "inline-block" }}
                >
                  Files
                </a>
              </div>
            </VideoRow>
          ))
        )}
      </Section>

      {/* Video Preview Modal */}
      {previewVideo && (
        <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(0,0,0,0.85)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: 24 }} onClick={() => setPreviewVideo(null)}>
          <div style={{ maxWidth: 700, width: "100%", background: "#18181b", borderRadius: 12, overflow: "hidden", border: "1px solid #27272a" }} onClick={e => e.stopPropagation()}>
            <div style={{ padding: "16px 20px", borderBottom: "1px solid #27272a", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 15, fontWeight: 500, color: "#fafafa" }}>Preview</span>
              <button onClick={() => setPreviewVideo(null)} style={{ background: "none", border: "none", color: "#a1a1aa", fontSize: 20, cursor: "pointer" }}>×</button>
            </div>
            <video controls style={{ width: "100%", display: "block" }} src={previewVideo} />
            <div style={{ padding: "16px 20px", borderTop: "1px solid #27272a" }}>
              <div style={{ fontSize: 12, color: "#a1a1aa", marginBottom: 8 }}>Caption</div>
              <pre style={{ margin: 0, fontSize: 12, color: "#d4d4d8", whiteSpace: "pre-wrap", wordBreak: "break-word", maxHeight: 120, overflow: "auto" }}>{previewCaption}</pre>
              <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                <a href={previewVideo} download style={{ padding: "8px 16px", borderRadius: 6, border: "none", background: "#3b82f6", color: "#fff", fontSize: 13, fontWeight: 500, textDecoration: "none", display: "inline-block" }}>
                  ⬇ Download Video
                </a>
                <button onClick={() => { navigator.clipboard.writeText(previewCaption); setMessage("Caption copied!"); }} style={{ padding: "8px 16px", borderRadius: 6, border: "1px solid #3f3f46", background: "transparent", color: "#a1a1aa", fontSize: 13, cursor: "pointer" }}>
                  📋 Copy Caption
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StatusRow({ label, ready, optional }: { label: string; ready: boolean; optional?: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
      <div style={{ width: 8, height: 8, borderRadius: "50%", background: ready ? "#22c55e" : optional ? "#f59e0b" : "#ef4444" }} />
      <span style={{ color: "#a1a1aa" }}>{label}</span>
      <span style={{ color: ready ? "#86efac" : optional ? "#fcd34d" : "#fca5a5", fontSize: 12 }}>{ready ? "Ready" : optional ? "Optional" : "Missing"}</span>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ padding: "16px", borderRadius: 10, border: "1px solid #27272a", background: "rgba(255,255,255,0.02)" }}>
      <div style={{ fontSize: 28, fontWeight: 600, color }}>{value}</div>
      <div style={{ fontSize: 12, color: "#a1a1aa", marginTop: 4 }}>{label}</div>
    </div>
  );
}

function Section({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <h2 style={{ fontSize: 15, fontWeight: 500, margin: "0 0 12px", color: "#d4d4d8", display: "flex", alignItems: "center", gap: 8 }}>
        {title}
        <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 10, background: "#27272a", color: "#a1a1aa" }}>{count}</span>
      </h2>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>{children}</div>
    </div>
  );
}

function VideoRow({ video, children }: { video: QueueVideo; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", borderRadius: 8, border: "1px solid #27272a", background: "rgba(255,255,255,0.02)" }}>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 500, color: "#e4e4e7", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{video.filename}</div>
        <div style={{ fontSize: 11, color: "#71717a", marginTop: 2 }}>{video.status} {video.source_url && "• R2"}</div>
      </div>
      <div style={{ flexShrink: 0, marginLeft: 12 }}>{children}</div>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div style={{ padding: "24px", textAlign: "center", borderRadius: 8, border: "1px dashed #27272a", color: "#71717a", fontSize: 13 }}>{text}</div>
  );
}
