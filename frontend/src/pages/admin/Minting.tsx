import { ReloadOutlined } from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Card, Col, Empty, Pagination, Progress, Row, Space, Timeline, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Page } from "@/components/Page";
import { usePager } from "@/components/pagination";
import { CardTitle, Pill, StatCard } from "@/components/ui";
import { api } from "@/services/api";
import type { ArpEvent, ArpTicket, EgressScore } from "@/types/api";
import { fmtTime } from "@/utils/format";

const EVENT_PAGE_SIZE = 5;
const fillCard = { height: "100%", width: "100%", display: "flex", flexDirection: "column" as const };
const fillBody = { flex: 1, minHeight: 0, display: "flex", flexDirection: "column" as const };

function eventLabel(event: ArpEvent): string {
  if (event.type === "published") return `新票据入池 ${event.id}`;
  if (event.type === "pooled") return `池内票据 ${event.id}`;
  return `${event.type} ${event.id}`;
}

export default function Minting() {
  const ticketPager = usePager(5);
  const egressPager = usePager(3);
  const [eventPage, setEventPage] = useState(1);
  const arp = useQuery({ queryKey: ["admin", "arp"], queryFn: api.arpStatus, refetchInterval: 5_000 });
  const egress = useQuery({ queryKey: ["stats", "egress"], queryFn: api.egress, refetchInterval: 20_000 });
  const s = arp.data;
  const tickets = s?.tickets ?? [];
  const events = s?.events ?? [];
  const eventPages = Math.max(1, Math.ceil(events.length / EVENT_PAGE_SIZE));
  const eventCurrent = Math.min(eventPage, eventPages);
  const eventSlice = events.slice((eventCurrent - 1) * EVENT_PAGE_SIZE, eventCurrent * EVENT_PAGE_SIZE);
  const egressRows = egress.data ?? [];
  const ticketCols: ProColumns<ArpTicket>[] = [
    { title: "票据 ID", dataIndex: "id", ellipsis: true, copyable: true },
    { title: "出口", dataIndex: "egress_id", width: 140, render: (_, r) => <Typography.Text code>{r.egress_id}</Typography.Text> },
    { title: "已用 / 上限", width: 88, render: (_, r) => <span className="tnum">{r.uses} / {Math.min(r.max_uses, 10)}</span> },
    { title: "剩余 TTL", width: 72, render: (_, r) => <span className="tnum">{r.ttl_left_sec}s</span> },
    { title: "票龄", width: 64, render: (_, r) => <span className="tnum">{r.age_sec}s</span> },
    { title: "身份", width: 128, render: (_, r) => <Pill color={r.chrome_148 ? "success" : "error"}>{r.chrome_148 ? "Chrome 148" : "非 148"}</Pill> },
    { title: "入池时间", dataIndex: "minted_at", width: 160, render: (_, r) => fmtTime(r.minted_at) },
  ];
  const egressCols: ProColumns<EgressScore>[] = [
    { title: "住宅出口", dataIndex: "egress_id", render: (_, r) => <Typography.Text code>{r.egress_id}</Typography.Text> },
    { title: "提交成功", dataIndex: "success", width: 100, render: (_, r) => <span className="tnum">{r.success}</span> },
    { title: "提交失败", dataIndex: "failed", width: 100, render: (_, r) => <span className="tnum">{r.failed}</span> },
    { title: "成功率", width: 180, render: (_, r) => {
      const total = r.success + r.failed;
      const rate = total ? r.success / total : 0;
      return <Progress percent={Math.round(rate * 100)} size="small" status={total && rate < 0.85 ? "exception" : "normal"} />;
    } },
    { title: "状态", width: 90, render: (_, r) => {
      const total = r.success + r.failed;
      const rate = total ? r.success / total : 1;
      return <Pill color={!total ? "default" : rate < 0.85 ? "error" : "success"}>{!total ? "无样本" : rate < 0.85 ? "异常" : "健康"}</Pill>;
    } },
  ];
  const lastCaption = s?.harvester_seen_at
    ? `最近心跳 ${fmtTime(s.harvester_seen_at)}`
    : s?.last_publish?.ts
      ? `上次入池 ${fmtTime(s.last_publish.ts)} · 进程已停`
      : "采集器进程未连接";
  const maxUses = Math.min(s?.arp_max_uses ?? 10, 10);
  const ready = s?.ready ?? 0;
  return <Page title="铸票系统" subtitle="当前 ARP 池、采集器状态与出口提交记录（真实数据）" extra={<Button icon={<ReloadOutlined />} loading={arp.isFetching} onClick={() => { void arp.refetch(); void egress.refetch(); }}>立即刷新</Button>}>
    <Row gutter={[16, 16]}>
      <Col xs={12} xl={6}><StatCard loading={arp.isLoading} tone="blue" label="可用票据" value={ready} caption={`常备目标 ${s?.arp_pool_target ?? s?.arp_min_ready ?? "-"} 枚 · 最低 ${s?.arp_min_ready ?? "-"}`} /></Col>
      <Col xs={12} xl={6}><StatCard loading={arp.isLoading} tone="orange" label="最老票龄（秒）" value={s?.oldest_age_sec ?? 0} caption={`TTL ${s?.arp_ttl_seconds ?? "-"} 秒`} /></Col>
      <Col xs={12} xl={6}><StatCard loading={arp.isLoading} tone={s?.harvester_online ? "green" : "red"} label="采集器" value={s?.harvester_online ? "在线" : "离线"} caption={lastCaption} /></Col>
      <Col xs={12} xl={6}><StatCard loading={arp.isLoading} tone="purple" label="预计并发" value={ready * maxUses} caption={`${ready} 张 × 上限 ${maxUses}${s?.proxy_ready ? ` · ${s.mint_browser_count} 路热浏览器 · 每轮 ${s.arp_mint_batch ?? "-"} 枚` : " · 面板代理未配置"}`} /></Col>
    </Row>
    <Row gutter={[16, 16]} align="stretch" style={{ marginTop: 16 }}>
      <Col xs={24} xl={16} style={{ display: "flex" }}>
        <Card title={<CardTitle title="当前票据" subtitle="Redis 池内未过期 ARP，不含 token / 代理凭据" />} style={fillCard} styles={{ body: fillBody }}>
          <ProTable
            rowKey="id"
            ghost
            search={false}
            options={false}
            pagination={{ ...ticketPager.pagination(tickets.length), hideOnSinglePage: false }}
            loading={arp.isLoading}
            columns={ticketCols}
            dataSource={tickets}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="池为空，等待采集器铸票" /> }}
          />
        </Card>
      </Col>
      <Col xs={24} xl={8} style={{ display: "flex" }}>
        <Card title={<CardTitle title="最近入池" subtitle="采集器 POST 的真实事件" />} style={fillCard} styles={{ body: fillBody }}>
          {events.length === 0
            ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有入池记录" style={{ margin: "auto" }} />
            : <>
              <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
                <Timeline items={eventSlice.map((event) => ({
                  color: "green",
                  children: <Space direction="vertical" size={0}>
                    <Typography.Text>{eventLabel(event)}</Typography.Text>
                    <Typography.Text type="secondary">{fmtTime(event.ts)} · {event.egress_id}</Typography.Text>
                  </Space>,
                }))} />
              </div>
              <Pagination
                simple
                current={eventCurrent}
                pageSize={EVENT_PAGE_SIZE}
                total={events.length}
                onChange={setEventPage}
                showSizeChanger={false}
                style={{ alignSelf: "flex-end", marginTop: 8, marginBottom: 0 }}
              />
            </>}
        </Card>
      </Col>
    </Row>
    <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
      <Col span={24}>
        <Card title={<CardTitle title="出口提交统计" subtitle="按 egress 汇总的真实出图请求，不是模拟铸票数" />}>
          <ProTable
            rowKey="egress_id"
            ghost
            search={false}
            options={false}
            pagination={{ ...egressPager.pagination(egressRows.length), hideOnSinglePage: false }}
            loading={egress.isLoading}
            columns={egressCols}
            dataSource={egressRows}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有提交记录" /> }}
          />
        </Card>
      </Col>
    </Row>
  </Page>;
}
