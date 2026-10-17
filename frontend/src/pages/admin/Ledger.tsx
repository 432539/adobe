import { DownloadOutlined, PlusOutlined } from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Tabs } from "antd";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Page } from "@/components/Page";
import { usePager } from "@/components/pagination";
import { Pill } from "@/components/ui";
import { api } from "@/services/api";
import type { ConsumeRecord, RechargeRecord } from "@/types/api";
import { fmtCredits, fmtTime } from "@/utils/format";

const STATUS_TEXT = { success: "成功", pending: "处理中", failed: "失败" } as const;
const STATUS_COLOR = { success: "success", pending: "warning", failed: "error" } as const;

export default function Ledger() {
  const rechargePager = usePager();
  const consumePager = usePager();
  const recharge = useQuery({ queryKey: ["admin", "recharges", rechargePager.page, rechargePager.pageSize], queryFn: () => api.recharges(rechargePager.page, rechargePager.pageSize), placeholderData: keepPreviousData });
  const consume = useQuery({ queryKey: ["admin", "consumes", consumePager.page, consumePager.pageSize], queryFn: () => api.consumes(consumePager.page, consumePager.pageSize), placeholderData: keepPreviousData });
  const rechargeColumns: ProColumns<RechargeRecord>[] = [
    { title: "流水号", dataIndex: "id", width: 90, copyable: true },
    { title: "用户", dataIndex: "username", width: 130 },
    { title: "金额", dataIndex: "amount", width: 120, hideInSearch: true, render: (_, r) => <span className="tnum" style={{ color: "#16a34a" }}>+{fmtCredits(r.amount)}</span> },
    { title: "方式", dataIndex: "method", width: 100 },
    { title: "状态", dataIndex: "status", width: 100, render: (_, r) => <Pill color={STATUS_COLOR[r.status]}>{STATUS_TEXT[r.status]}</Pill> },
    { title: "操作员", dataIndex: "operator", hideInSearch: true, responsive: ["lg"], render: (_, r) => r.operator ?? "-" },
    { title: "时间", dataIndex: "created_at", width: 160, valueType: "dateTimeRange", render: (_, r) => fmtTime(r.created_at) },
  ];
  const consumeColumns: ProColumns<ConsumeRecord>[] = [
    { title: "流水号", dataIndex: "id", width: 90, copyable: true },
    { title: "用户", dataIndex: "username", width: 130 },
    { title: "任务 ID", dataIndex: "job_id", copyable: true, ellipsis: true },
    { title: "模型", dataIndex: "model", width: 160, ellipsis: true, responsive: ["md"] },
    { title: "消费", dataIndex: "amount", width: 110, hideInSearch: true, render: (_, r) => <span className="tnum">{fmtCredits(r.amount)}</span> },
    { title: "时间", dataIndex: "created_at", width: 160, valueType: "dateTimeRange", render: (_, r) => fmtTime(r.created_at) },
  ];
  const tableCard = { bodyStyle: { padding: 0 } };
  return (
    <Page title="财务记录" subtitle="充值与消费流水审计" extra={<><Button icon={<DownloadOutlined />}>导出</Button><Button type="primary" icon={<PlusOutlined />}>人工调账</Button></>}>
      <div className="tab-panel">
        <Tabs
          className="compact-tabs"
          size="small"
          items={[
            {
              key: "recharge",
              label: "充值记录",
              children: (
                <ProTable
                  rowKey="id"
                  loading={recharge.isLoading}
                  columns={rechargeColumns}
                  dataSource={recharge.data?.items ?? []}
                  search={{ labelWidth: "auto", span: 6 }}
                  options={{ density: true, fullScreen: true, reload: false }}
                  cardProps={tableCard}
                  pagination={rechargePager.pagination(recharge.data?.total)}
                />
              ),
            },
            {
              key: "consume",
              label: "消费记录",
              children: (
                <ProTable
                  rowKey="id"
                  loading={consume.isLoading}
                  columns={consumeColumns}
                  dataSource={consume.data?.items ?? []}
                  search={{ labelWidth: "auto", span: 6 }}
                  options={{ density: true, fullScreen: true, reload: false }}
                  cardProps={tableCard}
                  pagination={consumePager.pagination(consume.data?.total)}
                />
              ),
            },
          ]}
        />
      </div>
    </Page>
  );
}
