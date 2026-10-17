import { useQuery } from "@tanstack/react-query";
import { Button, Card, Col, Progress, Row, Skeleton, Space, Typography } from "antd";
import { useNavigate } from "react-router-dom";
import { Page } from "@/components/Page";
import { CardTitle, Hero, Pill, StatCard } from "@/components/ui";
import { api } from "@/services/api";
import type { TimeseriesPoint } from "@/types/api";
import { fmtCredits, fmtHourLabel, fmtPercent } from "@/utils/format";

function TrendChart({ data }: { data: TimeseriesPoint[] }) {
  if (!data.length) return <div className="trend-empty">暂无趋势数据</div>;
  const width = 1000, height = 260, padX = 36, padTop = 20, padBottom = 36;
  const max = Math.max(...data.map((p) => p.jobs), 1);
  const innerH = height - padTop - padBottom;
  const points = data.map((p, i) => ({
    ...p,
    x: padX + (i / Math.max(data.length - 1, 1)) * (width - padX * 2),
    y: padTop + innerH - (p.jobs / max) * innerH,
    label: fmtHourLabel(p.ts),
  }));
  const line = points.map((p) => `${p.x},${p.y}`).join(" ");
  const ticks = points.filter((_, i) => i % 4 === 0 || i === points.length - 1);
  return <div className="trend-chart">
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="24 小时生成任务趋势">
      {[0, .25, .5, .75, 1].map((r) => <line key={r} x1={padX} x2={width - padX} y1={padTop + r * innerH} y2={padTop + r * innerH} className="trend-grid" />)}
      <polygon points={`${padX},${height - padBottom} ${line} ${width - padX},${height - padBottom}`} className="trend-area" />
      <polyline points={line} className="trend-line" />
      {ticks.map((p) => <g key={p.ts}><circle cx={p.x} cy={p.y} r="3.5" className="trend-dot" /><text x={p.x} y={height - 10} textAnchor="middle" className="trend-label">{p.label}</text></g>)}
    </svg>
  </div>;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const overview = useQuery({ queryKey: ["stats", "overview"], queryFn: api.overview, refetchInterval: 30_000 });
  const series = useQuery({ queryKey: ["stats", "timeseries"], queryFn: api.timeseries, staleTime: 60_000 });
  const egress = useQuery({ queryKey: ["stats", "egress"], queryFn: api.egress, staleTime: 30_000 });
  const s = overview.data;
  const loading = overview.isLoading;
  return <Page title="系统总览" subtitle="运营数据、生成任务与铸票概况">
    <Hero title="统一管理控制台" description="用户、余额、生成任务、铸票与请求日志集中管理，数据实时统计如下。" actions={<><Button className="hero-btn" onClick={() => navigate("/admin/users")}>用户管理</Button><Button className="hero-btn" onClick={() => navigate("/admin/logs")}>请求日志</Button></>} />
    <Row gutter={[16, 16]}>
      <Col xs={12} xl={6}><StatCard loading={loading} tone="blue" compact label="今日 / 合计生成" value={s ? `${(s.jobs_today ?? 0).toLocaleString()} / ${(s.jobs_total ?? 0).toLocaleString()}` : "-"} caption={`成功率 ${s ? fmtPercent(s.jobs_success_rate) : "-"}`} /></Col>
      <Col xs={12} xl={6}><StatCard loading={loading} tone="green" compact label="今日 / 合计收入（积分）" value={s ? `${fmtCredits(s.revenue_today)} / ${fmtCredits(s.revenue_total)}` : "-"} caption={`活跃用户 ${s?.users_active_today ?? "-"}`} /></Col>
      <Col xs={12} xl={6}><StatCard loading={loading} tone="purple" label="可用票据" value={s?.arp_ready} caption={`最老票龄 ${s?.arp_oldest_age_sec ?? "-"} 秒`} /></Col>
      <Col xs={12} xl={6}><StatCard loading={loading} tone="orange" compact label="可用积分 / 可用" value={s ? `${(s.credits_available ?? 0).toLocaleString()} / ${(s.credits_total ?? 0).toLocaleString()}` : "-"} caption={`号池 ${s?.accounts_total ?? "-"} 个 / ${s?.accounts_active ?? "-"} 个`} /></Col>
    </Row>
    <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
      <Col xs={12} xl={6}><StatCard loading={loading} tone="blue" label="用户总数" value={s?.users_total?.toLocaleString()} caption="累计注册" /></Col>
      <Col xs={12} xl={6}><StatCard loading={loading} tone="green" label="号池" value={s ? `${s.accounts_total} / ${s.accounts_active}` : "-"} caption="总数 / 可用" /></Col>
      <Col xs={12} xl={6}><StatCard loading={loading} tone="red" label="失败任务" value={s ? Math.round(s.jobs_today * (1 - s.jobs_success_rate)) : "-"} caption="今日累计" /></Col>
      <Col xs={12} xl={6}><StatCard loading={loading} tone="orange" label="住宅出口" value={egress.data?.length} caption="在线出口数" /></Col>
    </Row>
    <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
      <Col xs={24} xl={15}><Card title={<CardTitle title="24 小时生成趋势" subtitle="每小时提交的生成任务数" />}>{series.isLoading ? <Skeleton active /> : <TrendChart data={series.data ?? []} />}</Card></Col>
      <Col xs={24} xl={9}><Card title={<CardTitle title="出口健康" subtitle="最近 5 个住宅出口铸票成功率" />} extra={<Button size="small" onClick={() => navigate("/admin/minting")}>铸票系统</Button>}>
        <Space direction="vertical" size={14} style={{ width: "100%" }}>
          {(egress.data ?? []).slice(0, 5).map((e) => { const total = e.success + e.failed; const rate = total ? e.success / total : 0; return <div key={e.egress_id}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}><Typography.Text code>{e.egress_id}</Typography.Text><Pill color={rate < .85 ? "error" : "success"}>{rate < .85 ? "异常" : "健康"}</Pill></div>
            <Progress percent={Math.round(rate * 100)} size="small" status={rate < .85 ? "exception" : "normal"} />
          </div>; })}
          {!egress.isLoading && !(egress.data ?? []).length ? <Typography.Text type="secondary">暂无出口数据</Typography.Text> : null}
        </Space>
      </Card></Col>
    </Row>
  </Page>;
}
