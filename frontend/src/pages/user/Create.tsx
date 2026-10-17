import { CloudUploadOutlined, PictureOutlined, PlayCircleOutlined, RocketOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Page } from "@/components/Page";
import { CardTitle } from "@/components/ui";
import { Alert, App, Button, Card, Col, Empty, Flex, Form, Grid, Input, Progress, Row, Segmented, Select, Space, Spin, Typography, Upload } from "antd";
import type { UploadFile } from "antd/es/upload/interface";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/services/api";
import type { GenerationJob, ModelInfo } from "@/types/api";
import { fmtCredits, newIdempotencyKey } from "@/utils/format";

type Mode = "t2i" | "i2i" | "t2v" | "i2v";
interface Values { model: string; prompt: string; aspect_ratio: string; resolution: string; duration?: number }

const MODE_OPTIONS = [
  { label: "文生图", value: "t2i", icon: <PictureOutlined /> },
  { label: "图生图", value: "i2i", icon: <CloudUploadOutlined /> },
  { label: "文生视频", value: "t2v", icon: <PlayCircleOutlined /> },
  { label: "图生视频", value: "i2v", icon: <PlayCircleOutlined /> },
];

function inMode(model: ModelInfo, mode: Mode): boolean {
  if (model.modes?.length) return model.modes.includes(mode);
  if (mode === "t2i" || mode === "i2i") return model.kind === "image";
  if (mode === "i2v") return model.id.startsWith("seedance-") || model.id === "gemini-omni-flash";
  return model.kind === "video";
}

export default function Create() {
  const [mode, setMode] = useState<Mode>("t2i");
  const [activeJob, setActiveJob] = useState<GenerationJob | null>(null);
  const [refFiles, setRefFiles] = useState<UploadFile[]>([]);
  const [form] = Form.useForm<Values>();
  const { message } = App.useApp();
  const screens = Grid.useBreakpoint();
  const qc = useQueryClient();
  const { data: models = [], isLoading } = useQuery({ queryKey: ["models"], queryFn: api.models, staleTime: 10 * 60_000 });
  const available = useMemo(() => models.filter((m) => inMode(m, mode)), [models, mode]);
  const selectedModelId = Form.useWatch("model", form);
  const selected = models.find((m) => m.id === selectedModelId);
  const needsRefs = mode === "i2i" || mode === "i2v";
  const maxRefs = selected?.max_reference_images || (mode === "i2v" ? 4 : 8);
  const isVideo = mode === "t2v" || mode === "i2v";

  useEffect(() => {
    const first = available[0];
    if (!first) return;
    const current = form.getFieldValue("model");
    if (available.some((m) => m.id === current)) return;
    form.setFieldsValue({
      model: first.id,
      aspect_ratio: first.aspect_ratios[0],
      resolution: first.resolutions[0],
      duration: first.durations?.[0] ?? 5,
    });
  }, [available, form]);

  const create = useMutation({
    mutationFn: async (v: Values) => {
      const files = refFiles
        .map((item) => item.originFileObj)
        .filter((item): item is NonNullable<typeof item> => Boolean(item))
        .slice(0, maxRefs);
      if (needsRefs && files.length < 1) {
        throw new Error("请先上传参考图");
      }
      return isVideo
        ? api.createVideo({ ...v, duration: v.duration ?? 5, idempotency_key: newIdempotencyKey() }, files)
        : api.createImage({ ...v, idempotency_key: newIdempotencyKey() }, files);
    },
    onError: (err) => {
      message.error(err instanceof Error ? err.message : "提交失败");
    },
    onSuccess: (job) => {
      setActiveJob(job); message.success("任务已提交");
      void qc.invalidateQueries({ queryKey: ["jobs"] });
      const timer = window.setInterval(async () => {
        const next = await api.job(job.id); setActiveJob({ ...next });
        if (["succeeded", "failed", "rejected"].includes(next.status)) window.clearInterval(timer);
      }, 900);
    },
  });

  const switchMode = (value: string | number) => {
    const next = value as Mode; setMode(next); setActiveJob(null); setRefFiles([]);
    const first = models.find((m) => inMode(m, next));
    form.setFieldsValue({
      model: first?.id,
      aspect_ratio: first?.aspect_ratios[0],
      resolution: first?.resolutions[0],
      duration: first?.durations?.[0] ?? 5,
    });
  };

  return (
    <Page title="创作中心" subtitle="文生图、图生图、文生视频、图生视频">
      <Segmented block options={MODE_OPTIONS} value={mode} onChange={switchMode} style={{ marginBottom: 16, maxWidth: 640 }} />
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={10} xl={8}>
          <Card title={<CardTitle title="生成参数" subtitle="选择模型并填写提示词" />}>
            <Spin spinning={isLoading}>
              <Form form={form} layout="vertical" initialValues={{ model: available[0]?.id ?? "nano-banana", aspect_ratio: "1:1", resolution: "1K", duration: 5 }} onFinish={(v) => create.mutate(v)}>
                <Form.Item name="model" label="模型" rules={[{ required: true }]}>
                  <Select
                    options={available.map((m) => ({
                      value: m.id,
                      label: `${m.name} · ${fmtCredits(m.price)} 积分${m.submit_ready ? "" : "（未接入上游）"}`,
                    }))}
                    onChange={(id) => {
                      const next = models.find((m) => m.id === id);
                      const current = form.getFieldValue("resolution");
                      if (next && !next.resolutions.includes(current)) {
                        form.setFieldsValue({ resolution: next.resolutions[0] });
                      }
                    }}
                  />
                </Form.Item>
                {selected && !selected.submit_ready && (
                  <Alert type="warning" showIcon style={{ marginBottom: 16 }} message="该模型已列入系统并按计费表报价，上游请求体尚未接入，提交会失败退款。" />
                )}
                <Form.Item name="prompt" label="提示词" rules={[{ required: true, message: "请输入提示词" }, { max: 4000 }]}>
                  <Input.TextArea rows={screens.xs ? 5 : 7} showCount maxLength={4000} placeholder="描述你想要生成的画面、风格、光线与构图…" />
                </Form.Item>
                {needsRefs && (
                  <Form.Item label={`参考图片（最多 ${maxRefs} 张）`}>
                    <Upload.Dragger
                      multiple
                      listType="picture"
                      beforeUpload={() => false}
                      maxCount={maxRefs}
                      fileList={refFiles}
                      accept="image/png,image/jpeg,image/webp"
                      onChange={({ fileList }) => setRefFiles(fileList)}
                    >
                      <p><CloudUploadOutlined style={{ fontSize: 22, color: "#1677ff" }} /></p>
                      <p style={{ margin: 0 }}>拖拽或点击上传参考图。本地文件直接提交，不用先转成链接。</p>
                    </Upload.Dragger>
                  </Form.Item>
                )}
                <Row gutter={12}>
                  <Col span={12}><Form.Item name="aspect_ratio" label="宽高比"><Select options={(selected?.aspect_ratios ?? ["1:1"]).map((v) => ({ value: v, label: v }))} /></Form.Item></Col>
                  <Col span={12}><Form.Item name="resolution" label="分辨率"><Select options={(selected?.resolutions ?? ["1K"]).map((v) => ({ value: v, label: v }))} /></Form.Item></Col>
                </Row>
                {isVideo && <Form.Item name="duration" label="时长"><Select options={(selected?.durations ?? [5, 8, 10]).map((v) => ({ value: v, label: `${v} 秒` }))} /></Form.Item>}
                <Button type="primary" htmlType="submit" block icon={<RocketOutlined />} loading={create.isPending}>开始生成{selected ? ` · ${fmtCredits(selected.price)} 积分` : ""}</Button>
              </Form>
            </Spin>
          </Card>
        </Col>
        <Col xs={24} lg={14} xl={16}>
          <Card title={<CardTitle title="生成结果" subtitle="实时进度与结果预览" />} style={{ minHeight: screens.xs ? 400 : 620 }}>
            {!activeJob ? <Flex align="center" justify="center" style={{ minHeight: 500 }}><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="填写参数并提交，生成结果将在这里展示" /></Flex> : (
              <Space direction="vertical" size={16} style={{ width: "100%" }}>
                <Flex justify="space-between"><Typography.Text>{activeJob.model}</Typography.Text><Typography.Text type="secondary">任务 {activeJob.id}</Typography.Text></Flex>
                <Progress percent={activeJob.progress} status={activeJob.status === "failed" ? "exception" : activeJob.status === "succeeded" ? "success" : "active"} />
                {activeJob.status === "succeeded" && activeJob.result_urls.map((url) => <img key={url} src={url} alt="生成结果" style={{ width: "100%", maxHeight: 600, objectFit: "contain", borderRadius: 4 }} />)}
              </Space>
            )}
          </Card>
        </Col>
      </Row>
    </Page>
  );
}
