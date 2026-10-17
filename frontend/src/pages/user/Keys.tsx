import { CopyOutlined, PlusOutlined } from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Alert, App, Button, Form, Input, Modal, Popconfirm, Typography } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Page } from "@/components/Page";
import { usePager } from "@/components/pagination";
import { Pill } from "@/components/ui";
import { api } from "@/services/api";
import type { ApiKey } from "@/types/api";
import { fmtTime } from "@/utils/format";

export default function Keys() {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const pager = usePager();
  const [open, setOpen] = useState(false);
  const [created, setCreated] = useState<string>();
  const { data = [], isLoading } = useQuery({ queryKey: ["keys"], queryFn: api.keys });
  const create = useMutation({ mutationFn: api.createKey, onSuccess: (key) => { setCreated(key.plain); setOpen(false); void qc.invalidateQueries({ queryKey: ["keys"] }); } });
  const revoke = useMutation({ mutationFn: api.revokeKey, onSuccess: () => { message.success("KEY 已吊销"); void qc.invalidateQueries({ queryKey: ["keys"] }); } });
  const columns: ProColumns<ApiKey>[] = [
    { title: "名称", dataIndex: "name", ellipsis: true },
    { title: "KEY", dataIndex: "key_prefix", copyable: true, width: 180 },
    { title: "状态", dataIndex: "status", width: 100, render: (_, r) => <Pill color={r.status === "active" ? "success" : "default"}>{r.status === "active" ? "启用" : "已吊销"}</Pill> },
    { title: "RPM", dataIndex: "rate_limit", width: 80, responsive: ["md"] },
    { title: "最后使用", dataIndex: "last_used_at", width: 160, responsive: ["lg"], render: (_, r) => fmtTime(r.last_used_at) },
    { title: "创建时间", dataIndex: "created_at", width: 160, responsive: ["xl"], render: (_, r) => fmtTime(r.created_at) },
    { title: "操作", valueType: "option", width: 90, render: (_, r) => r.status === "active" ? <Popconfirm title="确认吊销？此操作不可恢复" onConfirm={() => revoke.mutate(r.id)}><Button size="small" danger>吊销</Button></Popconfirm> : null },
  ];
  return (
    <Page title="KEY 管理" subtitle="用于 OpenAI / Gemini 兼容接口 · KEY 仅在创建时完整显示一次" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>创建 KEY</Button>}>
      <ProTable rowKey="id" search={false} columns={columns} dataSource={data} loading={isLoading} pagination={pager.pagination(data.length)} />
      <Modal title="创建 API KEY" open={open} footer={null} onCancel={() => setOpen(false)} destroyOnClose>
        <Form layout="vertical" onFinish={({ name }: { name: string }) => create.mutate(name)}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input placeholder="例如：生产环境" /></Form.Item>
          <Button block type="primary" htmlType="submit" loading={create.isPending}>创建</Button>
        </Form>
      </Modal>
      <Modal title="请立即保存此 KEY" open={!!created} onOk={() => setCreated(undefined)} onCancel={() => setCreated(undefined)} cancelButtonProps={{ style: { display: "none" } }}>
        <Alert type="success" showIcon message="此 KEY 关闭后不再显示" />
        <Typography.Paragraph copyable={{ icon: <CopyOutlined /> }} code style={{ marginTop: 16, wordBreak: "break-all" }}>{created}</Typography.Paragraph>
      </Modal>
    </Page>
  );
}
