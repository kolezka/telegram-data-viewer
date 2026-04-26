import { useRef } from "react";
import { api } from "../api/client";

interface MediaEntry {
  filename?: string;
  media_type?: string;
  account?: string;
  width?: number | null;
  height?: number | null;
}

interface Props {
  item: MediaEntry;
  defaultAccount: string;
  className?: string;
  onClick?: () => void;
}

/**
 * Renders an inline thumbnail for a single media item: photo/sticker/gif as <img>,
 * video as <video> seeked past the black opening frame, anything else as a small
 * download chip. Falls back to a placeholder if the file is missing on disk.
 */
export default function MediaTile({ item, defaultAccount, className, onClick }: Props) {
  const account = item.account ?? defaultAccount;
  const filename = item.filename;
  const type = item.media_type ?? "document";
  const videoRef = useRef<HTMLVideoElement | null>(null);

  if (!filename || !account) {
    return <Placeholder type={type} className={className} />;
  }

  const url = api.mediaUrl(account, filename);

  const handleVideoLoaded = () => {
    const v = videoRef.current;
    if (!v) return;
    const seekTo = Number.isFinite(v.duration) && v.duration > 0
      ? Math.min(1, v.duration / 4)
      : 0;
    if (seekTo > 0) {
      try { v.currentTime = seekTo; } catch { /* ignore */ }
    }
  };

  const replaceWithPlaceholder = (e: React.SyntheticEvent<HTMLImageElement | HTMLVideoElement>) => {
    const el = e.currentTarget;
    const parent = el.parentElement;
    if (!parent) return;
    const ph = document.createElement("div");
    ph.className = "w-full h-full flex items-center justify-center text-xs text-gray-500 p-2 break-all bg-gray-100";
    ph.textContent = `(missing ${type})`;
    parent.replaceChild(ph, el);
  };

  if (type === "photo" || type === "sticker" || type === "gif") {
    return (
      <button onClick={onClick} className={className} type="button">
        <img
          src={url}
          alt={filename}
          loading="lazy"
          onError={replaceWithPlaceholder}
          className="w-full h-full object-cover"
        />
      </button>
    );
  }

  if (type === "video") {
    return (
      <button onClick={onClick} className={className} type="button">
        <video
          ref={videoRef}
          src={url}
          preload="metadata"
          muted
          playsInline
          onLoadedMetadata={handleVideoLoaded}
          onError={replaceWithPlaceholder}
          className="w-full h-full object-cover"
        />
      </button>
    );
  }

  return <Placeholder type={type} filename={filename} className={className} onClick={onClick} />;
}

function Placeholder({ type, filename, className, onClick }: { type: string; filename?: string; className?: string; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`${className ?? ""} w-full h-full flex items-center justify-center text-xs text-gray-500 p-2 break-all bg-gray-100`}
    >
      {filename ?? type}
    </button>
  );
}
