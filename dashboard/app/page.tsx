"use client";
import { useState, useEffect, useCallback, useRef } from "react";

interface QueueVideo {
  filename: string;
  status: string;
  source_url?: string;
  uploaded_at: string | null;
  processed_at: string | null;
}

interface VersionInfo {
  number: number;
  folder: string;
  robustness: string;
  speakers_found: string[];
  voiceover_duration: number;
  back_translation_score: number;
}

const ROBUSTNESS_LEVELS = [
  { key: "free", name: "Free", color: "#22c55e", trans: "Google Translate", voice: "gTTS (robotic)", speakers: "None", cost: 0.00 },
  { key: "basic", name: "Basic", color: "#3b82f6", trans: "GPT-4o-mini", voice: "OpenAI single", speakers: "Basic", cost: 0.02 },
  { key: "standard", name: "Standard", color: "#f59e0b", trans: "GPT-4o", voice: "Multi-voice", speakers: "GPT-4o", cost: 0.05 },
  { key: "hardened", name: "Hardened", color: "#ef4444", trans: "Dual + back-check", voice: "Multi-voice + gaps", speakers: "GPT-4o + pyannote", cost: 0.10 },
  { key: "maximum", name: "Maximum", color: "#a855f7", trans: "All + rules", voice: "All + gap tuning", speakers: "All + review", cost: 0.12 },
];

export default function Dashboard() {
  // Auth
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");

  // Core state
  const [videos, setVideos] = useState<QueueVideo[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [envStatus, setEnvStatus] = useState<any>(null);
  const [checkingEnv, setCheckingEnv] = useState(true);
  const [processingFile, setProcessingFile] = useState<string | null>(null);
  const [robustness, setRobustness] = useState("standard");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Preview
  const [previewVideo, setPreviewVideo] = useState<string | null>(null);
  const [previewFilename, setPreviewFilename] = useState<string>("");
  const [previewCaption, setPreviewCaption] = useState<string>("");
  const [previewVersions, setPreviewVersions] = useState<VersionInfo[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<number>(0);
  const [videoTime, setVideoTime] = useState(0);
  const [videoDuration, setVideoDuration] = useState(0);
  const videoRef = useRef<HTMLVideoElement>(null);

  // Auth check on mount
  useEffect(() => {
    const token = localStorage.getItem("naran_auth");
    if (token) setIsAuthenticated(true);
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    checkEnv();
    fetchQueue();
    const interval = setInterval(fetchQueue, 10000);
    return () => clearInterval(interval);
  }, [isAuthenticated]);

  useEffect(() => {
    if (processingFile) {
      const completed = videos.find(v => v.filename === processingFile && v.status === "completed");
      if (completed) {
        setProcessingFile(null);
        setMessage("Processing complete! Video ready.");
      }
    }
  }, [videos, processingFile]);

  async function login() {
    setAuthError("");
    try {
      const res = await fetch("/api/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      const data = await res.json();
      if (data.success) {
        localStorage.setItem("naran_auth", data.token);
        setIsAuthenticated(true);
      } else {
        setAuthError("Invalid password");
      }
    } catch (e) {
      setAuthError("Login error");
    }
  }

  async function checkEnv() {
    try {
      const res = await fetch("/api/env-check");
      const data = await res.json();
      setEnvStatus(data);
    } catch (e) {
      setEnvStatus({ ready: false });
    } finally {
      setCheckingEnv(false);
    }
  }

  async function fetchQueue() {
    try {
      const res = await fetch("https://raw.githubusercontent.com/Hamlet-Tamaz/naran-english-translation-pipeline/main/queue.json?t=" + Date.now());
      const data = await res.json();
      setVideos(data.videos || []);
    } catch (e) {}
  }

  async function fetchVersions(filename: string) {
    const videoId = filename.replace(".mp4", "");
    try {
      const res = await fetch(`https://raw.githubusercontent.com/Hamlet-Tamaz/naran-english-translation-pipeline/main/processed/${videoId}/versions.json?t=${Date.now()}`);
      if (!res.ok) return [];
      const data = await res.json();
      return data.versions || [];
    } catch (e) { return []; }
  }

  async function triggerPipeline(filename: string) {
    setProcessingFile(filename);
    setMessage(`Processing [${robustness}]... Takes ~5-10 minutes.`);
    try {
      const res = await fetch("/api/trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename, robustness }),
      });
      const data = await res.json();
      setMessage(data.message || "Pipeline triggered!");
    } catch (e) {
      setMessage("Error triggering pipeline.");
      setProcessingFile(null);
    }
  }

  async function openPreview(filename: string) {
    setPreviewFilename(filename);
    const versions = await fetchVersions(filename);
    setPreviewVersions(versions);
    const vNum = versions.length > 0 ? versions[versions.length - 1].number : 1;
    setSelectedVersion(vNum);
    loadVersionPreview(filename, vNum);
  }

  async function loadVersionPreview(filename: string, vNum: number) {
    const videoId = filename.replace(".mp4", "");
    setPreviewVideo(`https://raw.githubusercontent.com/Hamlet-Tamaz/naran-english-translation-pipeline/main/processed/${videoId}/v${vNum}/final.mp4`);
    try {
      const res = await fetch(`https://raw.githubusercontent.com/Hamlet-Tamaz/naran-english-translation-pipeline/main/processed/${videoId}/v${vNum}/caption.txt`);
      setPreviewCaption(await res.text());
    } catch (e) { setPreviewCaption(""); }
    setVideoTime(0); setVideoDuration(0);
  }

  async function uploadFile(file: File) {
    setUploadProgress(0);
    setMessage(`Uploading ${file.name}...`);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch("/api/upload", { method: "POST", body: formData });
      const data = await res.json();
      if (res.ok) {
        setMessage(`Uploaded ${file.name}!`);
        setUploadProgress(100);
        fetchQueue();
      } else {
        setMessage(`Error: ${data.message || "Upload failed"}`);
      }
    } catch (e: any) {
      setMessage(`Error: ${e.message}`);
    }
  }

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith("video/")) uploadFile(file);
    else setMessage("Error: Please drop a video file");
  }, []);

  const onDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); }, []);
  const onDragLeave = useCallback((e: React.DragEvent) => { e.preventDefault(); setIsDragging(false); }, []);

  const handleTimeUpdate = () => {
    if (videoRef.current) {
      setVideoTime(videoRef.current.currentTime);
      setVideoDuration(videoRef.current.duration || 0);
    }
  };

  const handleScrub = (e: React.ChangeEvent<HTMLInputElement>) => {
    const time = parseFloat(e.target.value);
    setVideoTime(time);
    if (videoRef.current) videoRef.current.currentTime = time;
  };

  const currentLevel = ROBUSTNESS_LEVELS.find(l => l.key === robustness) || ROBUSTNESS_LEVELS[2];
  const pending = videos.filter(v => v.status === "pending_approval");
  const completed = videos.filter(v => v.status === "completed");
  const githubReady = envStatus?.github_ready ?? false;

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, '0')}`;
  };

  // LOGIN SCREEN
  if (!isAuthenticated) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#0a0a0a" }}>
        <div style={{ width: 360, padding: 40, borderRadius: 16, border: "1px solid #27272a", background: "#18181b" }}>
          <h1 style={{ fontSize: 24, fontWeight: 600, color: "#fafafa", margin: "0 0 8px" }}>Naran Pipeline</h1>
          <p style={{ fontSize: 13, color: "#a1a1aa", margin: "0 0 24px" }}>Armenian content → English translation</p>
          <input
            type="password"
            placeholder="Enter password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            onKeyDown={e => e.key === "Enter" && login()}
            style={{ width: "100%", padding: "12px 14px", borderRadius: 8, border: "1px solid #3f3f46", background: "#27272a", color: "#fafafa", fontSize: 14, marginBottom: 12, outline: "none" }}
          />
          {authError && <div style={{ color: "#ef4444", fontSize: 12, marginBottom: 12 }}>{authError}</div>}
          <button onClick={login} style={{ width: "100%", padding: "12px", borderRadius: 8, border: "none", background: "#3b82f6", color: "#fff", fontSize: 14, fontWeight: 500, cursor: "pointer" }}>
            Sign In
          </button>
        </div>
      </div>
    );
  }

  // MAIN DASHBOARD
  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "32px 16px" }}>
      <header style={{ marginBottom: 32, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1 style={{ fontSize: 28, fontWeight: 600, margin: 0, color: "#fafafa" }}>Naran Pipeline</h1>
          <p style={{ margin: "8px 0 0", color: "#a1a1aa", fontSize: 14 }}>Armenian content → English translation, voiceover & subtitles</p>
        </div>
        <button onClick={() => { localStorage.removeItem("naran_auth"); setIsAuthenticated(false); }} style={{ padding: "8px 16px", borderRadius: 6, border: "1px solid #3f3f46", background: "transparent", color: "#a1a1aa", fontSize: 12, cursor: "pointer" }}>
          Sign Out
        </button>
      </header>

      {/* Robustness Slider */}
      <div style={{ padding: "18px", borderRadius: 12, border: "1px solid #27272a", background: "rgba(255,255,255,0.02)", marginBottom: 24 }}>
        <div style={{ fontSize: 13, fontWeight: 500, color: "#d4d4d8", marginBottom: 12 }}>Translation Robustness</div>
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          {ROBUSTNESS_LEVELS.map((level, i) => (
            <button
              key={level.key}
              onClick={() => setRobustness(level.key)}
              style={{
                flex: 1, padding: "10px 8px", borderRadius: 8, border: "1px solid",
                borderColor: robustness === level.key ? level.color : "#27272a",
                background: robustness === level.key ? `${level.color}20` : "transparent",
                color: robustness === level.key ? level.color : "#71717a",
                fontSize: 12, fontWeight: 500, cursor: "pointer", textAlign: "center"
              }}
            >
              <div style={{ fontSize: 11, marginBottom: 2 }}>{level.name}</div>
              <div style={{ fontSize: 10, opacity: 0.7 }}>${level.cost.toFixed(2)}</div>
            </button>
          ))}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 12, color: "#a1a1aa" }}>
          <div>Translation: <span style={{ color: "#d4d4d8" }}>{currentLevel.trans}</span></div>
          <div>Voiceover: <span style={{ color: "#d4d4d8" }}>{currentLevel.voice}</span></div>
          <div>Speakers: <span style={{ color: "#d4d4d8" }}>{currentLevel.speakers}</span></div>
          <div>Est. cost: <span style={{ color: currentLevel.color, fontWeight: 600 }}>${currentLevel.cost.toFixed(2)}/video</span></div>
        </div>
      </div>

      {message && (
        <div style={{ padding: "12px 16px", borderRadius: 8, marginBottom: 20, background: message.includes("Error") ? "rgba(239,68,68,0.15)" : message.includes("complete") ? "rgba(34,197,94,0.15)" : "rgba(59,130,246,0.15)", color: message.includes("Error") ? "#fca5a5" : message.includes("complete") ? "#86efac" : "#93c5fd", fontSize: 14 }}>
          {message}
        </div>
      )}

      {!checkingEnv && (
        <div style={{ padding: "14px 18px", borderRadius: 10, marginBottom: 24, border: "1px solid #27272a", background: "rgba(255,255,255,0.02)" }}>
          <div style={{ fontSize: 13, fontWeight: 500, color: "#d4d4d8", marginBottom: 10 }}>System Status</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <StatusRow label="GitHub API" ready={githubReady} />
            <StatusRow label="OpenAI Voiceover" ready={true} />
            <StatusRow label="Cloud Storage (R2)" ready={envStatus?.r2_ready} optional />
            <StatusRow label="Speaker Diarization" ready={!!envStatus?.checks?.HF_TOKEN} optional />
          </div>
        </div>
      )}

      {/* Upload */}
      <div onDrop={onDrop} onDragOver={onDragOver} onDragLeave={onDragLeave} onClick={() => fileInputRef.current?.click()}
        style={{ padding: "40px 24px", borderRadius: 12, border: `2px dashed ${isDragging ? "#3b82f6" : "#3f3f46"}`, background: isDragging ? "rgba(59,130,246,0.08)" : "rgba(255,255,255,0.02)", textAlign: "center", cursor: "pointer", transition: "all 0.2s ease", marginBottom: 32 }}>
        <input ref={fileInputRef} type="file" accept="video/*" onChange={e => e.target.files?.[0] && uploadFile(e.target.files[0])} style={{ display: "none" }} />
        <div style={{ fontSize: 32, marginBottom: 8 }}>📤</div>
        <div style={{ fontSize: 15, fontWeight: 500, color: "#d4d4d8" }}>Drop a video here, or click to browse</div>
        <div style={{ fontSize: 12, color: "#71717a", marginTop: 6 }}>MP4, MOV — any size via R2</div>
        {uploadProgress > 0 && uploadProgress < 100 && (
          <div style={{ marginTop: 16 }}>
            <div style={{ height: 4, borderRadius: 2, background: "#27272a", overflow: "hidden" }}>
              <div style={{ height: "100%", width: `${uploadProgress}%`, background: "#3b82f6", borderRadius: 2, transition: "width 0.3s ease" }} />
            </div>
          </div>
        )}
      </div>

      {/* Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 32 }}>
        <StatCard label="Pending" value={pending.length} color="#f59e0b" />
        <StatCard label="Processing" value={videos.filter(v => v.status === "processing").length + (processingFile ? 1 : 0)} color="#3b82f6" />
        <StatCard label="Completed" value={completed.length} color="#22c55e" />
      </div>

      {/* Pending */}
      <Section title="Pending Approval" count={pending.length}>
        {pending.length === 0 ? <EmptyState text="No videos waiting. Upload one above." /> : (
          pending.map(v => (
            <VideoRow key={v.filename} video={v}>
              {processingFile === v.filename ? (
                <span style={{ fontSize: 13, color: "#3b82f6", fontWeight: 500 }}>⏳ [{robustness}] Processing...</span>
              ) : (
                <button onClick={() => triggerPipeline(v.filename)} disabled={!!processingFile}
                  style={{ padding: "8px 16px", borderRadius: 6, border: "none", background: currentLevel.color, color: "#fff", fontSize: 13, fontWeight: 500, cursor: processingFile ? "not-allowed" : "pointer", opacity: processingFile ? 0.6 : 1 }}>
                  Process [{robustness}]
                </button>
              )}
            </VideoRow>
          ))
        )}
      </Section>

      {/* Completed */}
      <Section title="Completed" count={completed.length}>
        {completed.length === 0 ? <EmptyState text="No processed videos yet." /> : (
          completed.map(v => (
            <VideoRow key={v.filename} video={v}>
              <div style={{ display: "flex", gap: 8 }}>
                <button onClick={() => openPreview(v.filename)} style={{ padding: "8px 16px", borderRadius: 6, border: "1px solid #3b82f6", background: "transparent", color: "#3b82f6", fontSize: 13, fontWeight: 500, cursor: "pointer" }}>▶ Watch</button>
                <button onClick={() => triggerPipeline(v.filename)} disabled={loading || !!processingFile}
                  style={{ padding: "8px 16px", borderRadius: 6, border: "1px solid #f59e0b", background: "transparent", color: "#f59e0b", fontSize: 13, fontWeight: 500, cursor: (loading || processingFile) ? "not-allowed" : "pointer", opacity: (loading || processingFile) ? 0.6 : 1 }}>
                  🔄 Re-process
                </button>
              </div>
            </VideoRow>
          ))
        )}
      </Section>

      {/* Preview Modal */}
      {previewVideo && (
        <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(0,0,0,0.9)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: 24, overflow: "auto" }} onClick={() => setPreviewVideo(null)}>
          <div style={{ maxWidth: 800, width: "100%", background: "#18181b", borderRadius: 12, overflow: "hidden", border: "1px solid #27272a" }} onClick={e => e.stopPropagation()}>
            <div style={{ padding: "16px 20px", borderBottom: "1px solid #27272a", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 15, fontWeight: 500, color: "#fafafa" }}>Preview</span>
              <button onClick={() => setPreviewVideo(null)} style={{ background: "none", border: "none", color: "#a1a1aa", fontSize: 20, cursor: "pointer" }}>×</button>
            </div>

            {previewVersions.length > 1 && (
              <div style={{ padding: "12px 20px", borderBottom: "1px solid #27272a", display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <span style={{ fontSize: 12, color: "#a1a1aa" }}>Version:</span>
                {previewVersions.map(v => (
                  <button key={v.number} onClick={() => { setSelectedVersion(v.number); loadVersionPreview(previewVideo?.split("/processed/")[1]?.split("/v")[0] + ".mp4" || "", v.number); }}
                    style={{ padding: "4px 10px", borderRadius: 4, border: "1px solid", borderColor: selectedVersion === v.number ? "#3b82f6" : "#3f3f46", background: selectedVersion === v.number ? "rgba(59,130,246,0.2)" : "transparent", color: selectedVersion === v.number ? "#3b82f6" : "#a1a1aa", fontSize: 12, cursor: "pointer" }}>
                    v{v.number} ({v.robustness})
                  </button>
                ))}
              </div>
            )}

            <video ref={videoRef} controls style={{ width: "100%", display: "block" }} src={previewVideo} onTimeUpdate={handleTimeUpdate} onLoadedMetadata={handleTimeUpdate} />

            {videoDuration > 0 && (
              <div style={{ padding: "8px 20px", borderBottom: "1px solid #27272a" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <span style={{ fontSize: 11, color: "#a1a1aa", minWidth: 36 }}>{formatTime(videoTime)}</span>
                  <input type="range" min={0} max={videoDuration} step={0.1} value={videoTime} onChange={handleScrub} style={{ flex: 1, accentColor: "#3b82f6" }} />
                  <span style={{ fontSize: 11, color: "#a1a1aa", minWidth: 36 }}>{formatTime(videoDuration)}</span>
                </div>
              </div>
            )}

            <div style={{ padding: "16px 20px" }}>
              <div style={{ fontSize: 12, color: "#a1a1aa", marginBottom: 8 }}>Caption</div>
              <pre style={{ margin: 0, fontSize: 12, color: "#d4d4d8", whiteSpace: "pre-wrap", wordBreak: "break-word", maxHeight: 150, overflow: "auto" }}>{previewCaption}</pre>
              <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                <a href={previewVideo} download style={{ padding: "8px 16px", borderRadius: 6, border: "none", background: "#3b82f6", color: "#fff", fontSize: 13, fontWeight: 500, textDecoration: "none", display: "inline-block" }}>⬇ Download Video</a>
                <button onClick={() => { navigator.clipboard.writeText(previewCaption); setMessage("Caption copied!"); }} style={{ padding: "8px 16px", borderRadius: 6, border: "1px solid #3f3f46", background: "transparent", color: "#a1a1aa", fontSize: 13, cursor: "pointer" }}>📋 Copy Caption</button>
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
        {title}<span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 10, background: "#27272a", color: "#a1a1aa" }}>{count}</span>
      </h2>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>{children}</div>
    </div>
  );
}

function VideoRow({ video, children }: { video: any; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", borderRadius: 8, border: "1px solid #27272a", background: "rgba(255,255,255,0.02)" }}>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 500, color: "#e4e4e7", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{video.filename}</div>
        <div style={{ fontSize: 11, color: "#71717a", marginTop: 2 }}>{video.status}</div>
      </div>
      <div style={{ flexShrink: 0, marginLeft: 12 }}>{children}</div>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <div style={{ padding: "24px", textAlign: "center", borderRadius: 8, border: "1px dashed #27272a", color: "#71717a", fontSize: 13 }}>{text}</div>;
}
