"use client";
import { useState, useEffect, useCallback, useRef } from "react";

interface QueueVideo {
  filename: string;
  status: string;
  uploaded_at: string | null;
  processed_at: string | null;
}

export default function Dashboard() {
  const [videos, setVideos] = useState<QueueVideo[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchQueue();
    const interval = setInterval(fetchQueue, 10000);
    return () => clearInterval(interval);
  }, []);

  async function fetchQueue() {
    try {
      const res = await fetch("https://raw.githubusercontent.com/Hamlet-Tamaz/naran-english-translation-pipeline/main/queue.json");
      const data = await res.json();
      setVideos(data.videos || []);
    } catch (e) {
      console.error("Failed to fetch queue", e);
    }
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

  async function uploadFile(file: File) {
    if (file.size > 100 * 1024 * 1024) {
      setMessage("Error: File too large. Max 100MB for direct upload. Use Git LFS for larger files.");
      return;
    }

    setUploadProgress(0);
    setMessage(`Uploading ${file.name}...`);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });

      const data = await res.json();
      if (res.ok) {
        setMessage(`Uploaded ${file.name}! It will appear in Pending shortly.`);
        setUploadProgress(100);
        fetchQueue();
      } else {
        setMessage(`Error: ${data.message || "Upload failed"}`);
        setUploadProgress(0);
      }
    } catch (e) {
      setMessage("Error uploading file. Check console.");
      setUploadProgress(0);
    }
  }

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith("video/")) {
      uploadFile(file);
    } else {
      setMessage("Error: Please drop a video file (MP4, MOV, etc.)");
    }
  }, []);

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const onDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const onFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) uploadFile(file);
  };

  const pending = videos.filter(v => v.status === "pending_approval");
  const completed = videos.filter(v => v.status === "completed");
  const processing = videos.filter(v => v.status === "processing");

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "32px 16px" }}>
      <header style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: 28, fontWeight: 600, margin: 0, color: "#fafafa" }}>
          Naran Pipeline
        </h1>
        <p style={{ margin: "8px 0 0", color: "#a1a1aa", fontSize: 14 }}>
          Armenian content → English translation, voiceover & subtitles
        </p>
      </header>

      {message && (
        <div style={{
          padding: "12px 16px", borderRadius: 8, marginBottom: 20,
          background: message.includes("Error") ? "rgba(239,68,68,0.15)" : "rgba(34,197,94,0.15)",
          color: message.includes("Error") ? "#fca5a5" : "#86efac", fontSize: 14
        }}>
          {message}
        </div>
      )}

      {/* Upload Drop Zone */}
      <div
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={() => fileInputRef.current?.click()}
        style={{
          padding: "40px 24px",
          borderRadius: 12,
          border: `2px dashed ${isDragging ? "#3b82f6" : "#3f3f46"}`,
          background: isDragging ? "rgba(59,130,246,0.08)" : "rgba(255,255,255,0.02)",
          textAlign: "center",
          cursor: "pointer",
          transition: "all 0.2s ease",
          marginBottom: 32,
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="video/*"
          onChange={onFileSelect}
          style={{ display: "none" }}
        />
        <div style={{ fontSize: 32, marginBottom: 8 }}>📤</div>
        <div style={{ fontSize: 15, fontWeight: 500, color: "#d4d4d8" }}>
          Drop a video here, or click to browse
        </div>
        <div style={{ fontSize: 12, color: "#71717a", marginTop: 6 }}>
          MP4, MOV, AVI — up to 100MB
        </div>
        {uploadProgress > 0 && uploadProgress < 100 && (
          <div style={{ marginTop: 16 }}>
            <div style={{
              height: 4, borderRadius: 2, background: "#27272a", overflow: "hidden"
            }}>
              <div style={{
                height: "100%", width: `${uploadProgress}%`,
                background: "#3b82f6", borderRadius: 2,
                transition: "width 0.3s ease"
              }} />
            </div>
            <div style={{ fontSize: 11, color: "#71717a", marginTop: 4 }}>
              Uploading...
            </div>
          </div>
        )}
      </div>

      {/* Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 32 }}>
        <StatCard label="Pending" value={pending.length} color="#f59e0b" />
        <StatCard label="Processing" value={processing.length} color="#3b82f6" />
        <StatCard label="Completed" value={completed.length} color="#22c55e" />
      </div>

      {/* Pending */}
      <Section title="Pending Approval" count={pending.length}>
        {pending.length === 0 ? (
          <EmptyState text="No videos waiting. Upload one above." />
        ) : (
          pending.map(v => (
            <VideoRow key={v.filename} video={v}>
              <button
                onClick={() => triggerPipeline(v.filename)}
                disabled={loading}
                style={{
                  padding: "8px 16px", borderRadius: 6, border: "none",
                  background: "#fafafa", color: "#18181b", fontSize: 13,
                  fontWeight: 500, cursor: loading ? "not-allowed" : "pointer",
                  opacity: loading ? 0.6 : 1
                }}
              >
                {loading ? "Starting..." : "Process"}
              </button>
            </VideoRow>
          ))
        )}
      </Section>

      {/* Completed */}
      <Section title="Completed" count={completed.length}>
        {completed.length === 0 ? (
          <EmptyState text="No processed videos yet." />
        ) : (
          completed.map(v => (
            <VideoRow key={v.filename} video={v}>
              <a
                href={`https://github.com/Hamlet-Tamaz/naran-english-translation-pipeline/tree/main/processed/${v.filename.replace(".mp4", "")}`}
                target="_blank"
                rel="noopener"
                style={{
                  padding: "8px 16px", borderRadius: 6, border: "1px solid #3f3f46",
                  background: "transparent", color: "#a1a1aa", fontSize: 13,
                  textDecoration: "none", display: "inline-block"
                }}
              >
                View Output
              </a>
            </VideoRow>
          ))
        )}
      </Section>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{
      padding: "16px", borderRadius: 10, border: "1px solid #27272a",
      background: "rgba(255,255,255,0.02)"
    }}>
      <div style={{ fontSize: 28, fontWeight: 600, color }}>{value}</div>
      <div style={{ fontSize: 12, color: "#a1a1aa", marginTop: 4 }}>{label}</div>
    </div>
  );
}

function Section({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <h2 style={{
        fontSize: 15, fontWeight: 500, margin: "0 0 12px",
        color: "#d4d4d8", display: "flex", alignItems: "center", gap: 8
      }}>
        {title}
        <span style={{
          fontSize: 11, padding: "2px 8px", borderRadius: 10,
          background: "#27272a", color: "#a1a1aa"
        }}>{count}</span>
      </h2>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {children}
      </div>
    </div>
  );
}

function VideoRow({ video, children }: { video: QueueVideo; children: React.ReactNode }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "12px 16px", borderRadius: 8, border: "1px solid #27272a",
      background: "rgba(255,255,255,0.02)"
    }}>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{
          fontSize: 13, fontWeight: 500, color: "#e4e4e7",
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis"
        }}>
          {video.filename}
        </div>
        <div style={{ fontSize: 11, color: "#71717a", marginTop: 2 }}>
          {video.status}
        </div>
      </div>
      <div style={{ flexShrink: 0, marginLeft: 12 }}>
        {children}
      </div>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div style={{
      padding: "24px", textAlign: "center", borderRadius: 8,
      border: "1px dashed #27272a", color: "#71717a", fontSize: 13
    }}>
      {text}
    </div>
  );
}
