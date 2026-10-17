import { DeleteOutlined, DownloadOutlined, PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { ModalForm, ProFormSelect, ProFormTextArea, ProTable, type ProColumns } from "@ant-design/pro-components";
import { App, Button, Col, Descriptions, Popconfirm, Row, Space } from "antd";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type Key } from "react";
import { Page } from "@/components/Page";
import { usePager } from "@/components/pagination";
import { Pill, StatCard } from "@/components/ui";
import { api, type AccountListFilters } from "@/services/api";
import type { UpstreamAccount } from "@/types/api";
import { fmtHourLabel, fmtTime } from "@/utils/format";

const STATUS_TEXT = { active: "可用", parked: "冷却中", ratelimited: "限流", dead: "失效" } as const;
const STATUS_COLOR = { active: "success", parked: "warning", ratelimited: "orange", dead: "error" } as const;
const PLAN_TEXT = { UNKNOWN: "待验证", HARD: "积分号", FREE: "免费号" } as const;
const STATUS_OPTIONS = [
  { label: "可用", value: "active" },
  { label: "冷却中", value: "parked" },
  { label: "限流", value: "ratelimited" },
  { label: "失效", value: "dead" },
];
const CREDITS_WARN_BELOW = 1000;

type AccountSearch = UpstreamAccount & { q?: string; credits_lt?: number };

export default function Accounts() {
  const pager = usePager();
  const qc = useQueryClient();
  const { message } = App.useApp();
  const [filters, setFilters] = useState<AccountListFilters>({});
  const [editing, setEditing] = useState<UpstreamAccount | null>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
  const importPollTimers = useRef<number[]>([]);

  useEffect(() => {
    return () => {
      importPollTimers.current.forEach((timer) => window.clearTimeout(timer));
    };
  }, []);

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["admin", "accounts", pager.page, pager.pageSize, filters],
    queryFn: () => api.accounts(pager.page, pager.pageSize, filters),
    placeholderData: keepPreviousData,
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin", "accounts"] });

  const toggle = useMutation({
    mutationFn: (r: UpstreamAccount) => api.patchAccount(r.id, { status: r.status === "active" ? "dead" : "active" }),
    onSuccess: () => {
      message.success("已更新状态");
      void refresh();
    },
  });
  const verifyAccount = useMutation({
    mutationFn: (id: number) => api.refreshAccount(id),
    onSuccess: (r) => {
      message.success(`验证成功 · ${r.credential_status} · 积分 ${r.credits_remaining} / ${r.credits_total} · ${PLAN_TEXT[r.plan_cap] ?? r.plan_cap}`);
      void refresh();
    },
  });
  const exporting = useMutation({
    mutationFn: () => api.exportAccounts(filters),
    onSuccess: ({ text, count }) => {
      const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `accounts-${new Date().toISOString().slice(0, 10)}.txt`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      message.success(`已导出 ${count} 条`);
    },
  });
  const deleting = useMutation({
    mutationFn: (ids: number[]) => api.deleteAccounts(ids),
    onSuccess: ({ deleted }) => {
      message.success(`已删除 ${deleted} 个账号`);
      setSelectedRowKeys([]);
      void refresh();
    },
  });

  const importForm = (
    <ModalForm<{ text: string }>
      key="import"
      title="导入 Cookie"
      width={560}
      trigger={<Button type="primary" icon={<PlusOutlined />}>导入</Button>}
      modalProps={{ destroyOnHidden: true }}
      onFinish={async ({ text }) => {
        const res = await api.importAccounts(text);
        message.success(
          `已入库 ${res.created} 条，跳过重复 ${res.skipped} 条，正在后台验积分`,
        );
        void refresh();
        importPollTimers.current.forEach((timer) => window.clearTimeout(timer));
        importPollTimers.current = [2000, 6000, 15000].map((ms) =>
          window.setTimeout(() => void refresh(), ms),
        );
        return true;
      }}
    >
      <ProFormTextArea
        name="text"
        label="Cookie（每行一个账号）"
        rules={[{ required: true }]}
        fieldProps={{
          rows: 8,
          placeholder: "user@example.com----ims_sid=...; aux_sid=...\nims_sid=...; aux_sid=...",
        }}
        extra="导入先入库立刻返回，后台验积分。2.5 走网页，其它模型走 FF-iOS；只有 HARD 积分号会参与调度"
      />
    </ModalForm>
  );

  const items = data?.items ?? [];
  const pendingVerify = items.filter((row) => row.credential_status !== "ready" || row.plan_cap === "UNKNOWN");
  const verifyPending = useMutation({
    mutationFn: async (rows: UpstreamAccount[]) => {
      let ok = 0;
      let fail = 0;
      for (const row of rows) {
        try {
          await api.refreshAccount(row.id);
          ok += 1;
        } catch {
          fail += 1;
        }
      }
      return { ok, fail, total: rows.length };
    },
    onSuccess: ({ ok, fail, total }) => {
      if (!total) {
        message.info("当前页没有待验证账号");
        return;
      }
      message.success(`已验证 ${ok}/${total}${fail ? `，失败 ${fail}` : ""}`);
      void refresh();
    },
  });
  const accountsTotal = data?.accounts_total ?? data?.total ?? 0;
  const parked = data?.accounts_parked ?? 0;
  const hard = data?.accounts_hard ?? 0;
  const creditsAvailable = data?.credits_available ?? 0;
  const creditsLow = creditsAvailable < CREDITS_WARN_BELOW;

  const columns: ProColumns<AccountSearch>[] = [
    { title: "账号", dataIndex: "q", hideInTable: true, colSize: 1, fieldProps: { placeholder: "脱敏邮箱关键字", style: { width: 168 } } },
    { title: "账号", dataIndex: "email_masked", copyable: true, ellipsis: true, width: 150, hideInSearch: true, align: "center" },
    { title: "套餐", dataIndex: "plan_cap", width: 90, hideInSearch: true, align: "center", render: (_, r) => <Pill color={r.plan_cap === "HARD" ? "processing" : "default"}>{PLAN_TEXT[r.plan_cap] ?? r.plan_cap}</Pill> },
    { title: "凭据", dataIndex: "credential_status", width: 90, hideInSearch: true, align: "center", render: (_, r) => <Pill color={r.credential_status === "ready" ? "success" : r.credential_status === "invalid" ? "error" : "default"}>{r.credential_status === "ready" ? "已验证" : r.credential_status === "invalid" ? "失效" : r.credential_status === "transient" ? "暂时异常" : "待验证"}</Pill> },
    {
      title: "状态",
      dataIndex: "status",
      width: 88,
      align: "center",
      valueType: "select",
      fieldProps: { options: STATUS_OPTIONS, allowClear: true, placeholder: "全部", style: { width: 112 } },
      render: (_, r) => <Pill color={STATUS_COLOR[r.status]}>{STATUS_TEXT[r.status]}</Pill>,
    },
    {
      title: "积分小于",
      dataIndex: "credits_lt",
      hideInTable: true,
      valueType: "digit",
      fieldProps: { min: 0, precision: 0, placeholder: "剩余积分", style: { width: 112 } },
    },
    { title: "剩余额度", width: 110, hideInSearch: true, align: "center", render: (_, r) => <span className="tnum">{r.credits_remaining} / {r.credits_total}</span> },
    { title: "冷却至", dataIndex: "parked_until", width: 88, hideInSearch: true, align: "center", render: (_, r) => r.parked_until ? fmtHourLabel(r.parked_until) : "-" },
    { title: "最近使用", dataIndex: "last_used_at", width: 88, hideInSearch: true, align: "center", render: (_, r) => r.last_used_at ? fmtHourLabel(r.last_used_at) : "-" },
    {
      title: "操作",
      valueType: "option",
      width: 220,
      align: "center",
      render: (_, r) => (
        <Space size={6}>
          <Button size="small" onClick={() => setEditing(r)}>编辑</Button>
          <Button
            size="small"
            loading={verifyAccount.isPending && verifyAccount.variables === r.id}
            onClick={() => verifyAccount.mutate(r.id)}
          >
            验证
          </Button>
          <Button size="small" danger={r.status === "active"} loading={toggle.isPending && toggle.variables?.id === r.id} onClick={() => toggle.mutate(r)}>
            {r.status === "active" ? "停用" : "启用"}
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <Page title="号池管理" subtitle="Cookie 加密入库；FF-iOS Device Grant 按需派生；短期 Access Token 永不落库。2.5 走网页，其它走移动端">
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}><StatCard tone="blue" label="账号" value={accountsTotal} caption="全站号池" /></Col>
        <Col xs={12} md={6}>
          <StatCard
            tone={creditsAvailable <= 0 ? "red" : creditsLow ? "orange" : "green"}
            label="可用积分"
            value={creditsAvailable.toLocaleString("zh-CN")}
            caption={creditsLow ? `低于 ${CREDITS_WARN_BELOW}，请及时补充` : "积分充足"}
          />
        </Col>
        <Col xs={12} md={6}><StatCard tone="orange" label="冷却中" value={parked} caption="全站 408 临时 park" /></Col>
        <Col xs={12} md={6}><StatCard tone="purple" label="积分号" value={hard} caption="全站 HARD，可参与调度" /></Col>
      </Row>
      <ProTable<AccountSearch>
        className="accounts-table"
        rowKey="id"
        loading={isLoading}
        columns={columns}
        dataSource={items}
        rowSelection={{
          selectedRowKeys,
          preserveSelectedRowKeys: true,
          onChange: setSelectedRowKeys,
        }}
        search={{
          labelWidth: "auto",
          span: 4,
          defaultCollapsed: false,
          collapseRender: false,
          optionRender: (_search, _form, dom) => [
            ...dom,
            <Button key="refresh" icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>刷新</Button>,
            <Button
              key="verify-pending"
              loading={verifyPending.isPending}
              disabled={!pendingVerify.length}
              onClick={() => verifyPending.mutate(pendingVerify)}
            >
              验证待验证{pendingVerify.length ? `（${pendingVerify.length}）` : ""}
            </Button>,
            importForm,
            <Button key="export" icon={<DownloadOutlined />} loading={exporting.isPending} onClick={() => exporting.mutate()}>导出</Button>,
            <Popconfirm
              key="delete"
              title={`确定删除所选 ${selectedRowKeys.length} 个账号？`}
              description="删除后无法恢复；灰度账号需先在系统设置中取消。"
              disabled={!selectedRowKeys.length}
              onConfirm={() => deleting.mutate(selectedRowKeys.map(Number))}
            >
              <Button
                danger
                icon={<DeleteOutlined />}
                disabled={!selectedRowKeys.length}
                loading={deleting.isPending}
              >
                删除所选{selectedRowKeys.length ? `（${selectedRowKeys.length}）` : ""}
              </Button>
            </Popconfirm>,
          ],
        }}
        pagination={pager.pagination(data?.total)}
        onSubmit={(params) => {
          const next: AccountListFilters = {};
          if (typeof params.q === "string" && params.q.trim()) next.q = params.q.trim();
          if (typeof params.status === "string" && params.status) next.status = params.status;
          if (typeof params.credits_lt === "number" && Number.isFinite(params.credits_lt)) next.credits_lt = params.credits_lt;
          setFilters(next);
          pager.setPage(1);
        }}
        onReset={() => {
          setFilters({});
          pager.setPage(1);
        }}
      />

      <ModalForm<{ status: UpstreamAccount["status"]; cookie?: string }>
        key={editing?.id ?? "none"}
        open={!!editing}
        title={editing ? `编辑账号 · ${editing.email_masked}` : "编辑账号"}
        width={520}
        onOpenChange={(open) => { if (!open) setEditing(null); }}
        modalProps={{ destroyOnHidden: true }}
        initialValues={editing ? { status: editing.status, cookie: editing.cookie ?? "" } : undefined}
        onFinish={async (values) => {
          if (!editing) return false;
          await api.patchAccount(editing.id, {
            status: values.status,
            cookie: values.cookie?.trim() || undefined,
          });
          message.success("已保存");
          setEditing(null);
          void refresh();
          return true;
        }}
      >
        {editing ? (
          <Descriptions
            size="small"
            bordered
            column={1}
            style={{ marginBottom: 16 }}
          >
            <Descriptions.Item label="运行身份">
              按模型分流：2.5 走网页 clio + ARP，其它走 FF-iOS
            </Descriptions.Item>
            <Descriptions.Item label="Cookie 根凭据">
              {editing.cookie ? <Pill color="success">已保存</Pill> : <Pill color="error">缺失</Pill>}
            </Descriptions.Item>
            <Descriptions.Item label="FF-iOS Device">
              {editing.ios_device_ready ? (
                <Pill color="success">已初始化</Pill>
              ) : (
                <Pill color="default">未初始化</Pill>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="验证状态">
              {editing.credential_status} · {editing.last_verified_at ? fmtTime(editing.last_verified_at) : "尚未验证"}
            </Descriptions.Item>
          </Descriptions>
        ) : null}
        <ProFormSelect name="status" label="状态" rules={[{ required: true }]} options={STATUS_OPTIONS} />
        <ProFormTextArea
          name="cookie"
          label="Cookie"
          fieldProps={{ rows: 5 }}
          extra="明文显示当前 Cookie。修改后加密覆盖入库，不存 Access Token"
        />
      </ModalForm>
    </Page>
  );
}
