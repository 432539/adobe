import { Pill } from "@/components/ui";
import type { JobStatus } from "@/types/api";

const map: Record<JobStatus, { color: string; text: string }> = {
  queued: { color: "default", text: "排队中" },
  running: { color: "processing", text: "生成中" },
  succeeded: { color: "success", text: "已完成" },
  failed: { color: "error", text: "失败" },
  rejected: { color: "warning", text: "内容拒绝" },
};

export function StatusTag({ status }: { status: JobStatus }) {
  const item = map[status];
  return <Pill color={item.color}>{item.text}</Pill>;
}
