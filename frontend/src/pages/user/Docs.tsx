import { CopyOutlined } from "@ant-design/icons";
import { Card, Collapse, Segmented, Space, Table, Tag, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Page } from "@/components/Page";
import { CardTitle, Pill } from "@/components/ui";
import { api } from "@/services/api";
import { OSS_REPO_LABEL, OSS_REPO_URL, SUPPORT_QQ_GROUP, SUPPORT_QQ_LABEL } from "@/constants/support";
import { fmtCredits } from "@/utils/format";

const openai = `curl https://your-domain.com/v1/images/generations \\\\\n  -H \"Authorization: Bearer sk-your-key\" \\\\\n  -H \"Content-Type: application/json\" \\\\\n  -H \"Idempotency-Key: unique-request-id\" \\\\\n  -d '{\"model\":\"gpt-image-2\",\"prompt\":\"a red apple\",\"size\":\"1024x1024\"}'`;
const gemini = `curl \"https://your-domain.com/v1beta/models/gpt-image-2:generateContent\" \\\\\n  -H \"x-goog-api-key: sk-your-key\" \\\\\n  -H \"Content-Type: application/json\" \\\\\n  -d '{\"contents\":[{\"parts\":[{\"text\":\"a red apple\"}]}]}'`;

export default function Docs() {
  const [protocol, setProtocol] = useState("OpenAI");
  const { data = [] } = useQuery({ queryKey: ["models"], queryFn: api.models, staleTime: 600_000 });
  const code = protocol === "OpenAI" ? openai : gemini;
  return <Page title="调用说明" subtitle={`Base URL: https://your-domain.com · 写请求建议携带 Idempotency-Key · 同步超时返回 task_id 可继续轮询 · ${SUPPORT_QQ_LABEL}`}>
    <Card title={<Segmented options={["OpenAI", "Gemini"]} value={protocol} onChange={(v) => setProtocol(String(v))} />}>
      <Typography.Text type="secondary">文生图 · 同步调用</Typography.Text>
      <Typography.Paragraph copyable={{ icon: <CopyOutlined /> }} style={{ marginTop: 8 }}><pre style={{ margin: 0, overflowX: "auto", padding: 16, borderRadius: 4, background: "#0d1117", color: "#e6edf3", fontSize: 13 }}>{code}</pre></Typography.Paragraph>
      <Collapse items={[
        { key: "async", label: "异步调用", children: <Space direction="vertical"><Typography.Text>OpenAI 添加 <Tag>Prefer: respond-async</Tag> 或 <Tag>?async=true</Tag>；Gemini 使用 <Tag>:predictLongRunning</Tag>，随后查询 operations。</Typography.Text></Space> },
        { key: "edit", label: "图片编辑", children: <Typography.Text>OpenAI 使用 multipart <Tag>/v1/images/edits</Tag>；Gemini 在 contents.parts 中同时传 text 与 inlineData/fileData。</Typography.Text> },
      ]} />
    </Card>
    <Card title={<CardTitle title="开源与技术支持" subtitle={SUPPORT_QQ_LABEL} />} style={{ marginTop: 16 }}>
      <Typography.Paragraph style={{ marginBottom: 8 }}>
        {OSS_REPO_LABEL}：<Typography.Link href={OSS_REPO_URL} target="_blank" rel="noreferrer">{OSS_REPO_URL}</Typography.Link>
      </Typography.Paragraph>
      <Typography.Text>接入、计费或出图问题请加 QQ 群 <Typography.Text copyable>{SUPPORT_QQ_GROUP}</Typography.Text>。</Typography.Text>
    </Card>
    <Card title={<CardTitle title="模型能力与计费" subtitle="按次计费，失败不扣费" />} style={{ marginTop: 16 }}>
      <Table rowKey="id" size="small" pagination={false} dataSource={data} columns={[
        { title: "模型", dataIndex: "name" }, { title: "类型", dataIndex: "kind", render: (v: string) => <Pill color={v === "image" ? "processing" : "purple"}>{v === "image" ? "图片" : "视频"}</Pill> },
        { title: "分辨率", dataIndex: "resolutions", responsive: ["md"], render: (v: string[]) => v.join(" / ") },
        { title: "编辑", dataIndex: "supports_edit", render: (v: boolean) => v ? <Pill color="success">支持</Pill> : "-" },
        { title: "单价", dataIndex: "price", render: (v: number) => `${fmtCredits(v)} 积分` },
      ]} />
    </Card>
  </Page>;
}
