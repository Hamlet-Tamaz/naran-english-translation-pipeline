"use client";
import { useState, useEffect } from "react";

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

      {/* Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 32 }}>
        <StatCard label="Pending" value={pending.length} color="#f59e0b" />
        <StatCard label="Processing" value={processing.length} color="#3b82f6" />
        <StatCard label="Completed" value={completed.length} color="#22c55e" />
      </div>

      {/* Pending */}
      <Section title="Pending Approval" count={pending.length}>
        {pending.length === 0 ? (
          <EmptyState text="No videos waiting. Upload one to incoming/ folder." />
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

      {/* Upload instructions */}
      <div style={{
        marginTop: 32, padding: 16, borderRadius: 10,
        border: "1px dashed #3f3f46", background: "rgba(255,255,255,0.02)"
      }}>
        <h3 style={{ fontSize: 14, fontWeight: 500, margin: "0 0 8px", color: "#d4d4d8" }}>
          How to upload a video
        </h3>
        <ol style={{ margin: 0, paddingLeft: 18, color: "#a1a1aa", fontSize: 13, lineHeight: 1.8 }}>
          <li>Go to the repo on GitHub</li>
          <li>Navigate to the <code style={{ background: "#27272a", padding: "2px 6px", borderRadius: 4 }}>incoming/</code> folder</li>
          <li>Click "Add file" → "Upload files"</li>
          <li>Commit the video</li>
          <li>Return here — it will appear in Pending within 15 min (or refresh)</li>
        </ol>
      </div>
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
