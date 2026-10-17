import { DownloadOutlined, ReloadOutlined } from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Descriptions, Drawer, Input, Select, Space, Typography } from "antd";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { CleanupMenu, type CleanupScope } from "@/components/CleanupMenu";
import { FilterBar } from "@/components/FilterBar";
import { MediaThumb } from "@/components/MediaThumb";
import { Page } from "@/components/Page";
import { StatusTag } from "@/components/StatusTag";
import { usePager } from "@/components/pagination";
import { useDebounced } from "@/hooks/useDebounced";
import { api } from "@/services/api";
import type { GenerationJob } from "@/types/api";
import { durationMs, fmtCredits, fmtModelLabel, fmtMs, fmtTime, formatJobError } from "@/utils/format";

function isFailed(row: GenerationJob): boolean {
  return row.status === "failed" || row.status === "rejected";
}

export default function History() {
  const pager = usePager();
  const client = useQueryClient();
  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState("");
  const [status, setStatus] = useState<string>();
  const [detail, setDetail] = useState<GenerationJob | null>(null);
  const [cleaning, setCleaning] = useState(false);
  const debouncedPrompt = useDebounced(prompt.trim(), 500);
  const debouncedModel = useDebounced(model.trim(), 500);
  const filters = {
    prompt: debouncedPrompt || undefined,
    model: debouncedModel || undefined,
    status,
  };
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["jobs", pager.page, pager.pageSize, filters],
    queryFn: () => api.jobs(pager.page, pager.pageSize, filters),
    placeholderData: keepPreviousData,
    refetchInterval: (query) =>
      (query.state.data?.items ?? []).some((row) => row.status === "queued" || row.status === "running")
        ? 5_000
        : false,
  });
  const live = (data?.items ?? []).some((row) => row.status === "queued" || row.status === "running");
  const [, setClock] = useState(0);
  useEffect(() => {
    if (!live) return;
    const id = window.setInterval(() => setClock((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [live]);

  const columns: ProColumns<GenerationJob>[] = [
    {
      title: "预览",
      width: 72,
      render: (_, row) => (
        <MediaThumb url={row.result_urls[0]} kind={row.kind} width={40} height={40} preview={Boolean(row.result_urls[0])} />
      ),
    },
    { title: "提示词", dataIndex: "prompt", ellipsis: true, copyable: true, width: 220 },
    {
      title: "模型",
      dataIndex: "model",
      width: 160,
      ellipsis: true,
      render: (_, row) =>
        fmtModelLabel(
          row.model,
          String(row.params?.resolution || ""),
          String(row.params?.aspect_ratio || ""),
        ),
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 110,
      render: (_, row) => <StatusTag status={row.status} />,
    },
    {
      title: "耗时",
      width: 90,
      responsive: ["md"],
      render: (_, row) => {
        const ms = durationMs(row.created_at, row.finished_at);
        return ms == null ? "—" : <span className="tnum">{fmtMs(ms)}</span>;
      },
    },
    { title: "消费", dataIndex: "cost", width: 90, responsive: ["lg"], render: (_, row) => <span className="tnum">{fmtCredits(row.cost)}</span> },
    { title: "创建时间", dataIndex: "created_at", width: 160, responsive: ["lg"], render: (_, row) => fmtTime(row.created_at) },
    {
      title: "操作",
      valueType: "option",
      width: 140,
      render: (_, row) => (
        <Space size={4}>
          {isFailed(row) ? <Button size="small" onClick={() => setDetail(row)}>详情</Button> : null}
          {row.result_urls[0] ? <Button size="small" icon={<DownloadOutlined />} href={row.result_urls[0]} target="_blank">下载</Button> : null}
        </Space>
      ),
    },
  ];

  return (
    <Page title="生成历史" subtitle="查看、筛选与下载全部生成结果">
      <FilterBar
        filters={
          <>
            <Input
              allowClear
              placeholder="筛选提示词"
              style={{ width: 220 }}
              value={prompt}
              onChange={(e) => { setPrompt(e.target.value); pager.setPage(1); }}
            />
            <Input
              allowClear
              placeholder="筛选模型"
              style={{ width: 180 }}
              value={model}
              onChange={(e) => { setModel(e.target.value); pager.setPage(1); }}
            />
            <Select
              allowClear
              placeholder="状态"
              style={{ width: 140 }}
              value={status}
              onChange={(value) => { setStatus(value); pager.setPage(1); }}
              options={[
                { label: "成功", value: "succeeded" },
                { label: "生成中", value: "generating" },
                { label: "失败", value: "failed" },
              ]}
            />
          </>
        }
        actions={
          <>
            <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>刷新</Button>
            <CleanupMenu
              loading={cleaning}
              onClean={async (scope: CleanupScope) => {
                setCleaning(true);
                try {
                  const res = await api.clearJobs(scope);
                  pager.setPage(1);
                  await client.invalidateQueries({ queryKey: ["jobs"] });
                  return res.deleted;
                } finally {
                  setCleaning(false);
                }
              }}
            />
          </>
        }
      />
      <ProTable
        rowKey="id"
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isLoading}
        search={false}
        pagination={pager.pagination(data?.total)}
        options={{ density: true, fullScreen: true }}
        locale={{ emptyText: <Typography.Text type="secondary">暂无生成记录</Typography.Text> }}
      />
      <Drawer title="失败详情" width={520} open={!!detail} onClose={() => setDetail(null)} destroyOnHidden>
        {detail && (
          <Descriptions column={1} size="small">
            <Descriptions.Item label="状态"><StatusTag status={detail.status} /></Descriptions.Item>
            {detail.error_code === "content_rejected" || detail.status === "rejected" ? (
              <Descriptions.Item label="类型">内容过敏</Descriptions.Item>
            ) : null}
            <Descriptions.Item label="错误信息">{formatJobError(detail.error_code, detail.error_message)}</Descriptions.Item>
            <Descriptions.Item label="提示词">
              <Typography.Paragraph copyable={detail.prompt ? { text: detail.prompt } : false} style={{ marginBottom: 0 }}>
                {detail.prompt || "—"}
              </Typography.Paragraph>
            </Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>
    </Page>
  );
}
