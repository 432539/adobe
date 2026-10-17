import { Card, Tag, type TagProps } from "antd";
import type { ReactNode } from "react";

/** 圆角胶囊状态标签，带前置圆点 */
export function Pill({ color, children, className }: { color?: TagProps["color"]; children: ReactNode; className?: string }) {
  return <Tag bordered={false} color={color} className={`pill${className ? ` ${className}` : ""}`}>{children}</Tag>;
}

export type StatTone = "blue" | "green" | "red" | "orange" | "purple";

/** 指标卡：左侧色条 + 标签 + 数值 + 说明 */
export function StatCard({ label, value, caption, tone = "blue", loading, compact }: {
  label: ReactNode;
  value: ReactNode;
  caption?: ReactNode;
  tone?: StatTone;
  loading?: boolean;
  compact?: boolean;
}) {
  return (
    <Card className={`stat-card stat-${tone}${compact ? " stat-compact" : ""}`} loading={loading} styles={{ body: { padding: "16px 18px" } }}>
      <div className="stat-label">{label}</div>
      <div className="stat-value tnum">{value ?? "-"}</div>
      {caption !== undefined && <div className="stat-caption">{caption}</div>}
    </Card>
  );
}

/** 卡片标题：主标题 + 一行说明 */
export function CardTitle({ title, subtitle }: { title: ReactNode; subtitle?: ReactNode }) {
  return (
    <div className="card-title">
      <div className="card-title-main">{title}</div>
      {subtitle && <div className="card-title-sub">{subtitle}</div>}
    </div>
  );
}

/** 页面顶部的品牌色横幅 */
export function Hero({ title, description, actions }: { title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="hero">
      <div className="hero-body">
        <div className="hero-title">{title}</div>
        {description && <div className="hero-desc">{description}</div>}
      </div>
      {actions && <div className="hero-actions">{actions}</div>}
    </div>
  );
}