import type { ReactNode } from "react";
import { Space } from "antd";

export function FilterBar({
  filters,
  actions,
}: {
  filters: ReactNode;
  actions: ReactNode;
}) {
  return (
    <div className="page-filter-bar">
      <Space wrap size={8}>{filters}</Space>
      <Space size={8}>{actions}</Space>
    </div>
  );
}
