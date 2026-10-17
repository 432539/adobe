import { CopyOutlined, PlusOutlined } from "@ant-design/icons";
import {
  ModalForm,
  ProFormDigit,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
  ProTable,
  type ProColumns,
} from "@ant-design/pro-components";
import { App, Button, Modal, Space, Typography } from "antd";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Page } from "@/components/Page";
import { usePager } from "@/components/pagination";
import { Pill } from "@/components/ui";
import { api } from "@/services/api";
import type { AdminUser, CreateUserRequest, CreateUserResponse } from "@/types/api";
import { fmtCredits, fmtTime } from "@/utils/format";

type MoneyTarget = { user: AdminUser; mode: "recharge" | "adjust" };

export default function Users() {
  const { message } = App.useApp();
  const qc = useQueryClient();
  const pager = usePager();
  const [created, setCreated] = useState<CreateUserResponse | null>(null);
  const [money, setMoney] = useState<MoneyTarget | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["admin", "users", pager.page, pager.pageSize],
    queryFn: () => api.users(pager.page, pager.pageSize),
    placeholderData: keepPreviousData,
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin", "users"] });

  const toggle = useMutation({
    mutationFn: (u: AdminUser) => api.patchUser(u.id, { status: u.status === "active" ? "disabled" : "active" }),
    onSuccess: (u) => {
      message.success(u.status === "active" ? "已启用" : "已禁用");
      void refresh();
    },
  });

  const columns: ProColumns<AdminUser>[] = [
    { title: "用户", dataIndex: "username", copyable: true, width: 130 },
    { title: "邮箱", dataIndex: "email", ellipsis: true },
    {
      title: "角色",
      dataIndex: "role",
      width: 80,
      hideInSearch: true,
      render: (_, r) => <Pill color={r.role === "admin" ? "processing" : "default"}>{r.role === "admin" ? "管理员" : "用户"}</Pill>,
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 90,
      valueEnum: { active: { text: "正常" }, disabled: { text: "禁用" } },
      render: (_, r) => <Pill color={r.status === "active" ? "success" : "error"}>{r.status === "active" ? "正常" : "禁用"}</Pill>,
    },
    { title: "余额", dataIndex: "balance", width: 110, hideInSearch: true, render: (_, r) => <span className="tnum">{fmtCredits(r.balance)}</span> },
    { title: "生成数", dataIndex: "job_count", width: 90, hideInSearch: true, responsive: ["lg"] },
    { title: "累计消费", dataIndex: "total_consumed", width: 110, hideInSearch: true, responsive: ["lg"], render: (_, r) => <span className="tnum">{fmtCredits(r.total_consumed)}</span> },
    { title: "最后登录", dataIndex: "last_login_at", width: 160, hideInSearch: true, responsive: ["xl"], render: (_, r) => fmtTime(r.last_login_at) },
    {
      title: "操作",
      valueType: "option",
      width: 200,
      render: (_, r) => (
        <Space size={6}>
          <Button size="small" onClick={() => setMoney({ user: r, mode: "recharge" })}>充值</Button>
          <Button size="small" onClick={() => setMoney({ user: r, mode: "adjust" })}>调账</Button>
          <Button size="small" danger={r.status === "active"} loading={toggle.isPending && toggle.variables?.id === r.id} onClick={() => toggle.mutate(r)}>
            {r.status === "active" ? "禁用" : "启用"}
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <Page
      title="用户管理"
      subtitle="新建用户自动生成一把初始 KEY；余额只能通过充值 / 调账变动，全部留流水"
      extra={
        <ModalForm<CreateUserRequest>
          title="新增用户"
          width={480}
          trigger={<Button type="primary" icon={<PlusOutlined />}>新增用户</Button>}
          initialValues={{ role: "user", initial_balance: 0 }}
          modalProps={{ destroyOnHidden: true }}
          onFinish={async (values) => {
            const res = await api.createUser({ ...values, initial_balance: Math.round((values.initial_balance ?? 0) * 100) });
            setCreated(res);
            void refresh();
            return true;
          }}
        >
          <ProFormText name="username" label="用户名" rules={[{ required: true }, { pattern: /^[A-Za-z0-9_.-]{2,64}$/, message: "2-64 位字母数字 _ . -" }]} />
          <ProFormText name="email" label="邮箱" rules={[{ required: true, type: "email" }]} />
          <ProFormText.Password name="password" label="初始密码" rules={[{ required: true, min: 8, message: "至少 8 位" }]} />
          <ProFormSelect name="role" label="角色" options={[{ label: "用户", value: "user" }, { label: "管理员", value: "admin" }]} />
          <ProFormDigit name="initial_balance" label="开户余额（元）" min={0} fieldProps={{ precision: 2 }} extra="以充值流水入账，可为 0" />
        </ModalForm>
      }
    >
      <ProTable rowKey="id" loading={isLoading} columns={columns} dataSource={data?.items ?? []} search={{ labelWidth: "auto" }} pagination={pager.pagination(data?.total)} />

      <Modal open={!!created} title="用户已创建" onCancel={() => setCreated(null)} footer={<Button type="primary" onClick={() => setCreated(null)}>我已保存</Button>} destroyOnHidden>
        {created && (
          <Space direction="vertical" size={10} style={{ width: "100%" }}>
            <Typography.Text>
              用户 <Typography.Text code>{created.user.username}</Typography.Text> 已创建，初始余额 {fmtCredits(created.user.balance)}。
            </Typography.Text>
            <Typography.Text type="danger">下面的初始 KEY 只显示这一次，关闭后无法再查看。</Typography.Text>
            <div className="proxy-preview">
              <div className="proxy-preview-label">default KEY</div>
              <Typography.Text className="proxy-preview-url" copyable={{ text: created.initial_key.plain ?? "", icon: <CopyOutlined /> }}>
                {created.initial_key.plain}
              </Typography.Text>
            </div>
          </Space>
        )}
      </Modal>

      <ModalForm<{ amount: number; remark: string }>
        key={money ? `${money.user.id}-${money.mode}` : "none"}
        open={!!money}
        title={money ? `${money.mode === "recharge" ? "充值" : "调账"} · ${money.user.username}（当前 ${fmtCredits(money.user.balance)}）` : ""}
        width={420}
        onOpenChange={(o) => !o && setMoney(null)}
        modalProps={{ destroyOnHidden: true }}
        onFinish={async (v) => {
          if (!money) return false;
          const cents = Math.round(v.amount * 100);
          const u =
            money.mode === "recharge"
              ? await api.rechargeUser(money.user.id, cents, v.remark ?? "")
              : await api.adjustUser(money.user.id, cents, v.remark);
          message.success(`已${money.mode === "recharge" ? "充值" : "调账"}，余额 ${fmtCredits(u.balance)}`);
          void refresh();
          return true;
        }}
      >
        <ProFormDigit
          name="amount"
          label={money?.mode === "recharge" ? "充值金额（元）" : "调账金额（元，负数扣减）"}
          rules={[{ required: true }]}
          min={money?.mode === "recharge" ? 0.01 : undefined}
          fieldProps={{ precision: 2 }}
          extra={money?.mode === "adjust" ? "扣减不能使余额为负，后端会拒绝" : undefined}
        />
        <ProFormTextArea name="remark" label="备注" rules={money?.mode === "adjust" ? [{ required: true, message: "调账必须填写备注" }] : []} fieldProps={{ rows: 2, maxLength: 255 }} />
      </ModalForm>
    </Page>
  );
}
