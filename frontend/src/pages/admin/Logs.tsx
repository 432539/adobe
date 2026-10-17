import { CopyOutlined, ReloadOutlined } from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { App, Button, Descriptions, Drawer, Input, Select, Space, Typography } from "antd";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { CleanupMenu, type CleanupScope } from "@/components/CleanupMenu";
import { FilterBar } from "@/components/FilterBar";
import { MediaThumb } from "@/components/MediaThumb";
import { Page } from "@/components/Page";
import { usePager } from "@/components/pagination";
import { Pill } from "@/components/ui";
import { useDebounced } from "@/hooks/useDebounced";
import { api } from "@/services/api";
import type { RequestLog } from "@/types/api";
import { durationMs, fmtModelLabel, fmtMs, fmtTime } from "@/utils/format";

const STATUS_LABEL: Record<string, string> = {
  succeeded: "成功",
  generating: "生成中",
  failed: "失败",
};

function modelWithRes(row: RequestLog): string {
  const ratio = String(row.aspect_ratio || row.params?.aspect_ratio || "");
  return fmtModelLabel(row.model, row.resolution, ratio);
}

function statusPill(status?: string) {
  const color = status === "succeeded" ? "success" : status === "generating" ? "processing" : "error";
  return <Pill color={color}>{STATUS_LABEL[status || ""] || status || "—"}</Pill>;
}

function jobDurationMs(row: RequestLog): number {
  if (row.job_status === "generating") {
    return durationMs(row.created_at) ?? row.latency_ms ?? 0;
  }
  return row.latency_ms ?? 0;
}

export default function Logs() {
  const pager = usePager();
  const { message } = App.useApp();
  const client = useQueryClient();
  const [kind, setKind] = useState<string>();
  const [status, setStatus] = useState<string>();
  const [username, setUsername] = useState("");
  const q = useDebounced(username.trim(), 500);
  const [detail, setDetail] = useState<RequestLog | null>(null);
  const [cleaning, setCleaning] = useState(false);

  const filters = { kind, status, q: q || undefined };
  const query = useQuery({
    queryKey: ["admin", "logs", pager.page, pager.pageSize, filters],
    queryFn: () => api.logs(pager.page, pager.pageSize, filters),
    placeholderData: keepPreviousData,
    refetchInterval: 5_000,
  });
  const live =
    (query.data?.items ?? []).some((row) => row.job_status === "generating")
    || detail?.job_status === "generating";
  const [, setClock] = useState(0);
  useEffect(() => {
    if (!live) return;
    const id = window.setInterval(() => setClock((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [live]);

  const copyText = async (text: string, ok = "已复制") => {
    if (!text) {
      message.warning("没有可复制的内容");
      return;
    }
    await navigator.clipboard.writeText(text);
    message.success(ok);
  };

  const openDetail = async (row: RequestLog) => {
    if (!row.job_id) {
      setDetail({ ...row, attempts: [row], attempt_count: 1 });
      return;
    }
    try {
      setDetail(await api.logDetail(row.job_id));
    } catch {
      setDetail({ ...row, attempts: [row], attempt_count: row.attempt_count || 1 });
    }
  };

  const columns: ProColumns<RequestLog>[] = [
    { title: "任务 ID", dataIndex: "job_id", copyable: true, ellipsis: true, width: 300 },
    {
      title: "模型",
      dataIndex: "model_label",
      ellipsis: true,
      width: 160,
      render: (_, r) => modelWithRes(r),
    },
    {
      title: "状态",
      dataIndex: "job_status",
      width: 100,
      render: (_, r) => statusPill(r.job_status),
    },
    { title: "用户", dataIndex: "username", width: 120, ellipsis: true, responsive: ["lg"] },
    { title: "耗时", dataIndex: "latency_ms", width: 90, render: (_, r) => <span className="tnum">{fmtMs(jobDurationMs(r))}</span> },
    { title: "请求次数", dataIndex: "attempt_count", width: 90, responsive: ["xl"] },
    { title: "时间", dataIndex: "created_at", width: 160, render: (_, r) => fmtTime(r.created_at) },
    {
      title: "操作",
      valueType: "option",
      width: 80,
      render: (_, r) => <Button size="small" onClick={() => void openDetail(r)}>详情</Button>,
    },
  ];

  const attempts = detail?.attempts?.length ? detail.attempts : detail ? [detail] : [];
  const results = detail?.result_urls ?? [];
  const upstream = detail?.upstream_urls?.length ? detail.upstream_urls : results;

  return (
    <Page title="请求日志" subtitle="按任务归并的调用记录；详情可查看每次请求">
      <FilterBar
        filters={
          <>
            <Select
              allowClear
              placeholder="模型"
              style={{ width: 140 }}
              value={kind}
              onChange={(value) => { setKind(value); pager.setPage(1); }}
              options={[{ label: "图片", value: "image" }, { label: "视频", value: "video" }]}
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
            <Input
              allowClear
              placeholder="用户搜索"
              style={{ width: 200 }}
              value={username}
              onChange={(e) => { setUsername(e.target.value); pager.setPage(1); }}
            />
          </>
        }
        actions={
          <>
            <Button icon={<ReloadOutlined />} loading={query.isFetching} onClick={() => void query.refetch()}>刷新</Button>
            <CleanupMenu
              loading={cleaning}
              onClean={async (scope: CleanupScope) => {
                setCleaning(true);
                try {
                  const res = await api.clearLogs(scope);
                  pager.setPage(1);
                  await client.invalidateQueries({ queryKey: ["admin", "logs"] });
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
        rowKey={(r) => r.job_id || String(r.id)}
        loading={query.isLoading}
        columns={columns}
        dataSource={query.data?.items ?? []}
        search={false}
        options={{ density: true, fullScreen: true, reload: () => void query.refetch() }}
        pagination={pager.pagination(query.data?.total)}
      />
      <Drawer
        title="请求详情"
        width={720}
        open={!!detail}
        onClose={() => setDetail(null)}
        destroyOnHidden
      >
        {detail && (
          <Space direction="vertical" size={20} style={{ width: "100%" }}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="模型">{modelWithRes(detail)}</Descriptions.Item>
              <Descriptions.Item label="渠道">{detail.channel || "—"}</Descriptions.Item>
              <Descriptions.Item label="用户">{detail.username || "—"}</Descriptions.Item>
              <Descriptions.Item label="任务 ID">
                <Typography.Text copyable={detail.job_id ? { text: detail.job_id } : false}>{detail.job_id || "—"}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="状态">{statusPill(detail.job_status)}</Descriptions.Item>
              <Descriptions.Item label="耗时"><span className="tnum">{fmtMs(jobDurationMs(detail))}</span></Descriptions.Item>
              <Descriptions.Item label="请求次数">{detail.attempt_count || attempts.length}</Descriptions.Item>
            </Descriptions>

            <div>
              <Typography.Text strong>提示词</Typography.Text>
              <Typography.Paragraph copyable={detail.prompt ? { text: detail.prompt } : false} style={{ marginTop: 8, marginBottom: 0 }}>
                {detail.prompt || "—"}
              </Typography.Paragraph>
            </div>

            {attempts.map((item, index) => {
              const requestText = JSON.stringify({ prompt: item.prompt ?? "", params: item.params ?? {} }, null, 2);
              const trace = item.trace ?? [];
              const traceText = trace.length ? JSON.stringify(trace, null, 2) : "";
              return (
                <div key={item.id} className="log-trace-step">
                  <Space wrap size={8} style={{ marginBottom: 8 }}>
                    <Typography.Text strong>第 {index + 1} 次请求</Typography.Text>
                    {statusPill(item.job_status || (item.outcome === "ok" ? "succeeded" : "failed"))}
                    <Pill color={item.status_code < 300 ? "success" : item.status_code < 500 ? "warning" : "error"}>
                      {item.status_code}
                    </Pill>
                    <span className="tnum">{fmtMs(item.attempt_latency_ms ?? item.latency_ms)}</span>
                  </Space>
                  <Descriptions column={1} size="small">
                    <Descriptions.Item label="端点">{item.endpoint}</Descriptions.Item>
                    <Descriptions.Item label="结果">{item.outcome === "ok" ? "成功" : item.outcome || "—"}</Descriptions.Item>
                    <Descriptions.Item label="重试">{item.retry_count}</Descriptions.Item>
                  </Descriptions>
                  <Space style={{ margin: "8px 0" }}>
                    <Typography.Text type="secondary">请求记录</Typography.Text>
                    <Button size="small" icon={<CopyOutlined />} onClick={() => void copyText(requestText, "已复制请求")}>复制</Button>
                  </Space>
                  <pre className="log-request-json">{requestText}</pre>
                  <div style={{ marginTop: 12 }}>
                    <Space style={{ marginBottom: 8 }}>
                      <Typography.Text strong>上游逐步原始日志</Typography.Text>
                      {trace.length > 0 && (
                        <Button size="small" icon={<CopyOutlined />} onClick={() => void copyText(traceText, "已复制上游日志")}>复制全部</Button>
                      )}
                    </Space>
                    {trace.length === 0 ? (
                      <Typography.Text type="secondary">暂无逐步日志（旧记录或未打到上游）</Typography.Text>
                    ) : (
                      <div className="log-trace-list">
                        {trace.map((step, stepIndex) => (
                          <div key={`${step.step || "step"}-${stepIndex}`} className="log-trace-step">
                            <Space wrap size={8} style={{ marginBottom: 6 }}>
                              <Typography.Text strong>{step.step || `步骤 ${stepIndex + 1}`}</Typography.Text>
                              {step.status_code ? (
                                <Pill color={step.status_code < 300 ? "success" : step.status_code < 500 ? "warning" : "error"}>
                                  {step.status_code}
                                </Pill>
                              ) : null}
                              {typeof step.latency_ms === "number" && step.latency_ms > 0 ? (
                                <span className="tnum">{fmtMs(step.latency_ms)}</span>
                              ) : null}
                              {step.note ? <Typography.Text type="secondary">{step.note}</Typography.Text> : null}
                            </Space>
                            {(step.method || step.url) && (
                              <Typography.Text type="secondary" ellipsis={{ tooltip: step.url }} style={{ display: "block", marginBottom: 6 }}>
                                {[step.method, step.url].filter(Boolean).join(" ")}
                              </Typography.Text>
                            )}
                            {step.error ? <Typography.Text type="danger">{step.error}</Typography.Text> : null}
                            {step.body !== undefined && (
                              <pre className="log-request-json">{JSON.stringify(step.body, null, 2)}</pre>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            <div>
              <Space style={{ marginBottom: 8 }}>
                <Typography.Text strong>上游返回的结果</Typography.Text>
                {upstream.length > 0 && (
                  <Button size="small" icon={<CopyOutlined />} onClick={() => void copyText(upstream.join("\n"), "已复制上游结果")}>复制全部</Button>
                )}
              </Space>
              {upstream.length === 0 ? (
                <Typography.Text type="secondary">暂无上游结果</Typography.Text>
              ) : (
                <div className="log-upstream-list">
                  {upstream.map((url, index) => (
                    <div key={`${url}-${index}`} className="log-upstream-line">
                      <Typography.Text copyable={{ text: url }} ellipsis={{ tooltip: url }}>
                        {url}
                      </Typography.Text>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div>
              <div style={{ marginBottom: 8 }}>
                <Typography.Text strong>结果</Typography.Text>
              </div>
              {results.length === 0 ? (
                <Typography.Text type="secondary">暂无结果可预览</Typography.Text>
              ) : (
                <Space wrap size={12}>
                  {results.map((url) => (
                    <div key={url} className="log-result-card">
                      <MediaThumb url={url} kind={detail.kind} width={240} height={160} />
                      <Button size="small" icon={<CopyOutlined />} onClick={() => void copyText(url, "已复制结果地址")}>复制</Button>
                    </div>
                  ))}
                </Space>
              )}
            </div>
          </Space>
        )}
      </Drawer>
    </Page>
  );
}
