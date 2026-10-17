import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Col, Row } from "antd";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Page } from "@/components/Page";
import { usePager } from "@/components/pagination";
import { Pill, StatCard } from "@/components/ui";
import { api } from "@/services/api";
import { useAuth } from "@/store/auth";
import type { LedgerEntry } from "@/types/api";
import { fmtCredits, fmtTime } from "@/utils/format";

const TYPE_TEXT = { recharge: "充值", consume: "消费", refund: "退款", adjust: "调整" } as const;

export default function Billing() {
  const profile = useAuth((s) => s.profile);
  const pager = usePager();
  const { data, isLoading } = useQuery({ queryKey: ["ledger", pager.page, pager.pageSize], queryFn: () => api.ledger(pager.page, pager.pageSize), placeholderData: keepPreviousData });
  const columns: ProColumns<LedgerEntry>[] = [
    { title: "类型", dataIndex: "type", width: 100, render: (_, r) => <Pill color={r.delta > 0 ? "success" : "processing"}>{TYPE_TEXT[r.type]}</Pill> },
    { title: "变动", dataIndex: "delta", width: 120, render: (_, r) => <span className="tnum" style={{ color: r.delta > 0 ? "#16a34a" : undefined }}>{r.delta > 0 ? "+" : ""}{fmtCredits(r.delta)}</span> },
    { title: "变动后余额", dataIndex: "balance_after", width: 130, responsive: ["md"], render: (_, r) => <span className="tnum">{fmtCredits(r.balance_after)}</span> },
    { title: "关联单号", dataIndex: "ref_id", copyable: true, ellipsis: true, responsive: ["lg"] },
    { title: "备注", dataIndex: "remark", ellipsis: true },
    { title: "时间", dataIndex: "created_at", width: 160, render: (_, r) => fmtTime(r.created_at) },
  ];
  return <Page title="余额明细" subtitle="所有余额变动均可追溯">
    <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
      <Col xs={24} md={8}><StatCard tone="blue" label="当前可用余额（积分）" value={fmtCredits(profile?.balance)} caption="实时余额" /></Col>
      <Col xs={12} md={8}><StatCard tone="orange" label="本月消费（积分）" value="3,286.00" caption="按自然月统计" /></Col>
      <Col xs={12} md={8}><StatCard tone="green" label="本月生成" value={428} caption="成功任务数" /></Col>
    </Row>
    <ProTable rowKey="id" search={false} loading={isLoading} columns={columns} dataSource={data?.items ?? []} pagination={pager.pagination(data?.total)} />
  </Page>;
}
