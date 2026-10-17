import { Image } from "antd";
import { useEffect, useState } from "react";

const VIDEO_EXT = /\.(mp4|webm|mov|m4v)(\?|#|$)/i;

export function isVideoAsset(url: string, kind?: string): boolean {
  if (kind === "video") return true;
  const path = url.split("?")[0] ?? url;
  return VIDEO_EXT.test(path);
}

export function MediaThumb({
  url,
  kind,
  width = 120,
  height = 120,
  preview = true,
}: {
  url?: string;
  kind?: string;
  width?: number;
  height?: number;
  preview?: boolean;
}) {
  const [asVideo, setAsVideo] = useState(() => Boolean(url && isVideoAsset(url, kind)));
  useEffect(() => {
    setAsVideo(Boolean(url && isVideoAsset(url, kind)));
  }, [url, kind]);

  if (!url) {
    return (
      <div
        style={{
          width,
          height,
          background: "var(--ant-color-fill-tertiary)",
          borderRadius: 8,
        }}
      />
    );
  }
  if (asVideo) {
    return (
      <video
        src={url}
        controls={preview}
        muted
        playsInline
        preload="metadata"
        width={width}
        height={height}
        style={{ objectFit: "cover", borderRadius: 8, background: "#000", display: "block" }}
      />
    );
  }
  return (
    <Image
      width={width}
      height={height}
      src={url}
      preview={preview}
      style={{ objectFit: "cover", borderRadius: 8 }}
      onError={() => setAsVideo(true)}
    />
  );
}
