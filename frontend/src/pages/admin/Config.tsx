import { ExperimentOutlined, PlusOutlined, ReloadOutlined, SaveOutlined } from "@ant-design/icons";
import { ProForm, ProFormDigit, ProFormSelect, ProFormSwitch, ProFormText } from "@ant-design/pro-components";
import { Alert, App, AutoComplete, Button, Col, Form, Input, InputNumber, Modal, Progress, Row, Space, Switch, Table, Tabs, Typography, type FormInstance } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type ReactNode } from "react";
import { Page } from "@/components/Page";
import { usePager } from "@/components/pagination";
import { Pill } from "@/components/ui";
import { api } from "@/services/api";
import type { ProxyConfig, ProxyTestResult, R2Account, SystemConfig } from "@/types/api";
import { parseProxyLine, previewProxyUrl, randomSid } from "@/utils/proxy";
import { fmtTime } from "@/utils/format";

const COUNTRIES = ["SG", "US", "JP", "HK", "TW", "KR", "GB", "DE", "FR", "CA", "AU"].map((v) => ({ value: v }));

/** 代理出口：粘贴一行自动拆字段；账号按 `{u}-region-{CC}-sid-{SID}-t-{N}` 模板生成 */
function ProxyPane({ form }: { form: FormInstance<SystemConfig> }) {
  const { message } = App.useApp();
  const [line, setLine] = useState("");
  const [sid, setSid] = useState(() => randomSid(8));
  const [result, setResult] = useState<ProxyTestResult>();
  const proxy = Form.useWatch("proxy", form) as ProxyConfig | undefined;
  const test = useMutation({ mutationFn: api.testProxy, onSuccess: setResult, onError: () => message.error("代理测试失败") });

  const preview = useMemo(() => (proxy?.host && proxy.username ? previewProxyUrl(proxy, sid.slice(0, proxy.sid_length || 8)) : ""), [proxy, sid]);

  const applyLine = () => {
    const parsed = parseProxyLine(line);
    if (!parsed) { message.warning("无法识别，支持 user:pass@host:port 或 host:port:user:pass"); return; }
    const current = form.getFieldValue("proxy") as ProxyConfig;
    form.setFieldValue("proxy", { ...current, ...parsed, password_set: current.password_set || Boolean(parsed.password) });
    setSid(randomSid(parsed.sid_length ?? current.sid_length ?? 8));
    setLine("");
    message.success(parsed.country ? `已解析：${parsed.country} · 会话 ${parsed.sticky_minutes} 分钟 · sid ${parsed.sid_length} 位` : "已解析地址与账号，请补充国家与时长");
  };

  const runTest = async () => {
    const values = form.getFieldValue("proxy") as ProxyConfig;
    if (!values?.host || !values.username || !values.country) { message.warning("请先填写地址、账号与国家"); return; }
    const next = randomSid(values.sid_length || 8);
    setSid(next);
    await test.mutateAsync(values);
  };

  return (
    <div className="cfg-pane">
      <Section title="代理出口" desc="住宅 sticky 代理。粘贴供应商给的整行代理串即可自动拆分为下方字段；铸票与提交共用同一会话，sid 每次铸票随机生成。">
        <Form.Item label="粘贴代理串自动解析" className="proxy-paste">
          <Input.Search
            value={line}
            onChange={(e) => setLine(e.target.value)}
            onSearch={applyLine}
            enterButton="解析填入"
            allowClear
            placeholder="p9mx1124350-region-SG-sid-2fyNrACK-t-10:password@us.arxlabs.io:3010"
          />
        </Form.Item>
        <Row gutter={16}>
          <Col xs={8} lg={3}><ProFormSelect name={["proxy", "scheme"]} label="协议" allowClear={false} options={[{ value: "http", label: "HTTP" }, { value: "socks5", label: "SOCKS5" }]} /></Col>
          <Col xs={16} lg={8}><ProFormText name={["proxy", "host"]} label="代理地址" placeholder="us.arxlabs.io" rules={[{ required: true, message: "必填" }]} /></Col>
          <Col xs={8} lg={3}><ProFormDigit name={["proxy", "port"]} label="端口" min={1} max={65535} fieldProps={{ precision: 0 }} rules={[{ required: true, message: "必填" }]} /></Col>
          <Col xs={16} lg={5}><ProFormText name={["proxy", "username"]} label="账号" placeholder="p9mx1124350" rules={[{ required: true, message: "必填" }]} /></Col>
          <Col xs={24} lg={5}>
            <ProFormText.Password
              name={["proxy", "password"]}
              label={<span>密码 {proxy?.password_set && <Pill color="success">已配置</Pill>}</span>}
              placeholder={proxy?.password_set ? "留空保持不变" : "代理密码"}
              fieldProps={{ autoComplete: "new-password" }}
            />
          </Col>
        </Row>
        <Row gutter={16}>
          <Col xs={8} lg={4}>
            <Form.Item name={["proxy", "country"]} label="国家 / 地区" rules={[{ required: true, message: "必填" }]} normalize={(v: string) => v?.toUpperCase()}>
              <AutoComplete options={COUNTRIES} placeholder="SG" filterOption={(t, o) => (o?.value as string).startsWith(t.toUpperCase())} />
            </Form.Item>
          </Col>
          <Col xs={8} lg={4}><ProFormDigit name={["proxy", "sticky_minutes"]} label="会话时长（分钟）" min={1} max={120} extra="必须 ≥ 向上取整((票TTL+60秒)/60)。TTL 5 分钟需要粘性 6 分钟，否则出口会在票过期前漂掉" fieldProps={{ precision: 0 }} /></Col>
          <Col xs={8} lg={4}><ProFormDigit name={["proxy", "sid_length"]} label="会话 ID 位数" min={4} max={32} fieldProps={{ precision: 0 }} /></Col>
          <Col xs={8} lg={4}>
            <Form.Item
              name={["proxy", "upload_via_proxy"]}
              label="传图走代理"
              valuePropName="checked"
              extra="参考图上传上游存储。默认直连；开启后走住宅 sticky。生成结果下载始终直连"
            >
              <Switch />
            </Form.Item>
          </Col>
        </Row>
      </Section>

      <Section title="生成测试" desc="按上方模板生成一枚随机 sid，经该出口探测连通性与实际落地国家" extra={
        <Space size={8}>
          <Button size="small" icon={<ReloadOutlined />} onClick={() => setSid(randomSid(proxy?.sid_length || 8))}>换一个 sid</Button>
          <Button size="small" type="primary" icon={<ExperimentOutlined />} loading={test.isPending} onClick={runTest}>生成并测试</Button>
        </Space>
      }>
        <div className="proxy-preview">
          <span className="proxy-preview-label">本次代理串</span>
          <Typography.Text className="proxy-preview-url" copyable={preview ? { text: preview } : false}>{preview || "填写地址与账号后生成"}</Typography.Text>
        </div>
        {result && (
          <div className="proxy-result">
            <div><span className="proxy-result-k">状态</span><Pill color={result.ok ? "success" : "error"}>{result.ok ? "连通" : "失败"}</Pill></div>
            <div><span className="proxy-result-k">出口 IP</span><span className="tnum">{result.egress_ip ?? "—"}</span></div>
            <div><span className="proxy-result-k">落地国家</span><span>{result.country ?? "—"}{result.country && proxy?.country && result.country !== proxy.country && <Typography.Text type="warning" style={{ marginLeft: 6 }}>与配置不一致</Typography.Text>}</span></div>
            <div><span className="proxy-result-k">延迟</span><span className="tnum">{result.latency_ms !== undefined ? `${result.latency_ms} ms` : "—"}</span></div>
            {result.error && <div><span className="proxy-result-k">错误</span><Typography.Text type="danger">{result.error}</Typography.Text></div>}
          </div>
        )}
      </Section>
    </div>
  );
}

function FactoryWatchdog() {
  const arp = useQuery({ queryKey: ["admin", "arp"], queryFn: api.arpStatus, refetchInterval: 5_000 });
  const s = arp.data;
  const online = Boolean(s?.harvester_online);
  return (
    <>
      {s && !online && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 14 }}
          message="采集器看门狗离线"
          description="出图依赖池里未过期的 ARP。看门狗能拉起崩溃的浏览器、杀掉僵死 Chrome，但采集器进程本身必须在住宅出口机器上常驻。"
        />
      )}
      <div className="watchdog">
        <div className={`watchdog-cell ${online ? "is-on" : "is-off"}`}>
          <div className="watchdog-k">看门狗</div>
          <div className="watchdog-v">{arp.isLoading ? "…" : online ? "在线" : "离线"}</div>
          <div className="watchdog-s">{s?.harvester_seen_at ? `心跳 ${fmtTime(s.harvester_seen_at)}` : "进程未连接"}</div>
        </div>
        <div className="watchdog-cell">
          <div className="watchdog-k">可用票据</div>
          <div className="watchdog-v tnum">{s?.ready ?? 0}<span className="watchdog-den"> / {s?.arp_pool_target ?? s?.arp_min_ready ?? "-"}</span></div>
          <div className="watchdog-s">低于最低水位加速铸，满常备池停铸。提交轮询取票</div>
        </div>
        <div className="watchdog-cell">
          <div className="watchdog-k">票据 TTL</div>
          <div className="watchdog-v tnum">{s?.arp_ttl_seconds ?? "-"}s</div>
          <div className="watchdog-s">到期 Redis 自动销毁，宁早丢</div>
        </div>
        <div className="watchdog-cell">
          <div className="watchdog-k">并行浏览器</div>
          <div className="watchdog-v tnum">{s?.mint_browser_count ?? "-"}</div>
          <div className="watchdog-s">1–2 路热进程即可 · 间隔 {s?.mint_interval_seconds ?? "-"}s · 每轮 {s?.arp_mint_batch ?? "-"} 枚</div>
        </div>
      </div>
    </>
  );
}

/** 配置分节：标题 + 说明 + 内容，节与节之间用细线分隔 */
function Section({ title, desc, extra, children }: { title: ReactNode; desc?: ReactNode; extra?: ReactNode; children: ReactNode }) {
  return (
    <section className="cfg-section">
      <div className="cfg-section-head">
        <div>
          <div className="cfg-section-title">{title}</div>
          {desc && <div className="cfg-section-desc">{desc}</div>}
        </div>
        {extra}
      </div>
      {children}
    </section>
  );
}

/** 积分输入：后端存“分”（100 = 1.00 积分），界面按 2 位小数显示 */
function CreditInput({ name, unit }: { name: (string | number)[]; unit: string }) {
  return (
    <Form.Item name={name} noStyle>
      <InputNumber<number>
        className="credit-input"
        min={1}
        step={1}
        controls={false}
        formatter={(v) => (v === undefined || v === null ? "" : (Number(v) / 100).toFixed(2))}
        parser={(v) => Math.round(parseFloat((v ?? "").replace(/[^\d.]/g, "") || "0") * 100)}
        addonAfter={unit}
      />
    </Form.Item>
  );
}

const gb = (n?: number) => (n === undefined ? "—" : `${(n / 1024 ** 3).toFixed(1)} GB`);

const GB = 1024 ** 3;
const rowKey = (a: R2Account, i?: number) => a.id ?? `new-${i ?? 0}-${a.name}`;

/** R2 账号编辑弹窗：新增必须给完整 endpoint + 密钥；编辑时留空即保持 */
function R2AccountModal({ open, initial, onCancel, onOk }: { open: boolean; initial?: R2Account; onCancel: () => void; onOk: (a: R2Account) => void }) {
  const { message } = App.useApp();
  const [form] = Form.useForm<R2Account & { quota_gb: number }>();
  const test = useMutation({ mutationFn: api.testR2 });
  const isNew = !initial?.id;

  const draft = (): R2Account | null => {
    const v = form.getFieldsValue();
    if (!v.name || !v.bucket || (isNew && !v.endpoint)) { message.warning("请先填写名称、Endpoint 与 Bucket"); return null; }
    return { ...initial, ...v, quota_bytes: Math.round((v.quota_gb || 10) * GB), endpoint: v.endpoint || undefined, access_key_id: v.access_key_id || undefined, secret_access_key: v.secret_access_key || undefined };
  };

  return (
    <Modal
      open={open}
      title={isNew ? "新增 R2 账号" : `编辑 ${initial?.name}`}
      onCancel={onCancel}
      destroyOnClose
      width={640}
      footer={[
        <Button key="test" icon={<ExperimentOutlined />} loading={test.isPending} onClick={async () => {
          const d = draft(); if (!d) return;
          const r = await test.mutateAsync({ draft: d });
          r.ok ? message.success(`连通正常 · ${r.latency_ms} ms`) : message.error(r.error ?? "连接失败");
        }}>测试连接</Button>,
        <Button key="cancel" onClick={onCancel}>取消</Button>,
        <Button key="ok" type="primary" onClick={async () => { await form.validateFields(); const d = draft(); if (d) onOk(d); }}>{isNew ? "添加" : "确定"}</Button>,
      ]}
    >
      <Form form={form} layout="vertical" className="cfg-pane" style={{ padding: 0 }} initialValues={{ enabled: true, prefix: "", public_base_url: "", ...initial, quota_gb: (initial?.quota_bytes ?? 10 * GB) / GB }}>
        <Row gutter={16}>
          <Col span={8}><Form.Item name="name" label="名称" rules={[{ required: true, message: "必填" }]}><Input placeholder="cf1" /></Form.Item></Col>
          <Col span={16}><Form.Item name="endpoint" label="Endpoint" rules={isNew ? [{ required: true, message: "必填" }, { type: "url", message: "需为完整 URL" }] : [{ type: "url", message: "需为完整 URL" }]} extra={!isNew && initial?.endpoint_masked ? `当前：${initial.endpoint_masked}，留空保持不变` : undefined}><Input placeholder="https://<account_id>.r2.cloudflarestorage.com" /></Form.Item></Col>
          <Col span={8}><Form.Item name="bucket" label="Bucket" rules={[{ required: true, message: "必填" }]}><Input placeholder="pic2api-media" /></Form.Item></Col>
          <Col span={16}><Form.Item name="public_base_url" label="public_base_url" rules={[{ type: "url", message: "需为完整 URL" }]} extra="已生效的 r2.dev 或已绑定 DNS 的自定义域名"><Input placeholder="https://pub-xxxx.r2.dev" /></Form.Item></Col>
          <Col span={12}><Form.Item name="access_key_id" label="Access Key ID" rules={isNew ? [{ required: true, message: "必填" }] : []} extra={!isNew && initial?.key_suffix ? `当前 ••••${initial.key_suffix}，留空保持不变` : undefined}><Input autoComplete="off" /></Form.Item></Col>
          <Col span={12}><Form.Item name="secret_access_key" label="Secret Access Key" rules={isNew ? [{ required: true, message: "必填" }] : []} extra={!isNew ? "留空保持不变" : undefined}><Input.Password autoComplete="new-password" /></Form.Item></Col>
          <Col span={8}><Form.Item name="prefix" label="对象前缀"><Input placeholder="可选，如 media/" /></Form.Item></Col>
          <Col span={8}><Form.Item name="quota_gb" label="额度（GB）"><InputNumber min={1} max={1024} style={{ width: "100%" }} /></Form.Item></Col>
          <Col span={8}><Form.Item name="enabled" label="启用" valuePropName="checked"><Switch /></Form.Item></Col>
        </Row>
      </Form>
    </Modal>
  );
}

function R2Panel({ accounts, onChange }: { accounts: R2Account[]; onChange: (next: R2Account[]) => void }) {
  const { message, modal } = App.useApp();
  const pager = usePager(8);
  const [editing, setEditing] = useState<{ index: number | null; account?: R2Account } | null>(null);
  const [testing, setTesting] = useState<string>();
  const usage = useQuery({ queryKey: ["admin", "r2-usage"], queryFn: () => api.r2Usage(false), staleTime: 60_000, retry: false });
  const refresh = useMutation({ mutationFn: () => api.r2Usage(true), onSuccess: (d) => usage.refetch().then(() => message.success(`已刷新 · 合计 ${gb(d.total_used_bytes)}`)) });
  const usageById = new Map((usage.data?.accounts ?? []).map((u) => [u.id, u]));

  const commit = (next: R2Account[]) => {
    const pages = Math.max(1, Math.ceil(next.length / pager.pageSize));
    if (pager.page > pages) pager.setPage(pages);
    onChange(next);
  };

  const runTest = async (a: R2Account) => {
    const key = a.id ?? a.name;
    setTesting(key);
    try {
      const r = await api.testR2(a.id ? { id: a.id } : { draft: a });
      r.ok ? message.success(`${a.name} 连通正常 · ${r.latency_ms} ms`) : message.error(`${a.name}：${r.error ?? "连接失败"}`);
    } finally { setTesting(undefined); }
  };

  return (
    <>
      <div className="r2-toolbar">
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {usage.data ? <>合计已用 <span className="tnum">{gb(usage.data.total_used_bytes)}</span> / {gb(usage.data.total_quota_bytes)}{usage.data.accounts.some((u) => u.cached) && " · 用量来自缓存"}</> : usage.isFetching ? "读取用量…" : "用量未加载"}
        </Typography.Text>
        <Space size={8}>
          <Button size="small" icon={<ReloadOutlined />} loading={refresh.isPending} onClick={() => refresh.mutate()}>刷新用量</Button>
          <Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => setEditing({ index: null })}>新增账号</Button>
        </Space>
      </div>
      <Table<R2Account>
        rowKey={rowKey}
        size="small"
        pagination={{ ...pager.pagination(accounts.length), hideOnSinglePage: false }}
        className="cfg-table"
        dataSource={accounts}
        locale={{ emptyText: "尚未配置 R2 账号" }}
        columns={[
          { title: "账号", dataIndex: "name", width: 72, render: (v: string, r) => <span>{v}{!r.id && <span style={{ marginLeft: 6 }}><Pill color="warning">未保存</Pill></span>}</span> },
          { title: "Endpoint", width: 190, ellipsis: true, responsive: ["lg"], render: (_, r) => <Typography.Text type="secondary" style={{ fontSize: 12 }}>{r.endpoint ? r.endpoint.replace(/^https?:\/\//, "") : r.endpoint_masked}</Typography.Text> },
          { title: "Bucket", dataIndex: "bucket", width: 120, responsive: ["xl"] },
          { title: "public_base_url", dataIndex: "public_base_url", ellipsis: true, render: (v: string) => v ? <Typography.Link href={v} target="_blank" rel="noreferrer">{v}</Typography.Link> : <Typography.Text type="secondary">—</Typography.Text> },
          { title: "启用", dataIndex: "enabled", width: 60, render: (v: boolean, r) => <Switch size="small" checked={v} onChange={(c) => commit(accounts.map((a) => (a === r ? { ...a, enabled: c } : a)))} /> },
          { title: "用量 / 剩余", width: 170, render: (_, r) => {
            const u = r.id ? usageById.get(r.id) : undefined;
            if (u?.error) return <Typography.Text type="danger" style={{ fontSize: 12 }}>读取失败</Typography.Text>;
            const used = u?.used_bytes ?? r.used_bytes;
            if (used === undefined) return <Typography.Text type="secondary" style={{ fontSize: 12 }}>—</Typography.Text>;
            const pct = r.quota_bytes ? Math.min(100, Math.round((used / r.quota_bytes) * 100)) : 0;
            return <div><div className="tnum" style={{ fontSize: 12 }}>{gb(used)} / {gb(Math.max(0, r.quota_bytes - used))}{u?.truncated && " +"}</div><Progress percent={pct} size="small" showInfo={false} status={pct > 85 ? "exception" : "normal"} /></div>;
          } },
          { title: "密钥", width: 84, render: (_, r) => <Typography.Text type="secondary">••••{r.access_key_id ? r.access_key_id.slice(-4) : r.key_suffix ?? "----"}</Typography.Text> },
          { title: "", width: 150, render: (_, r) => (
            <Space size={4}>
              <Button size="small" loading={testing === (r.id ?? r.name)} onClick={() => runTest(r)}>测试</Button>
              <Button size="small" onClick={() => setEditing({ index: accounts.findIndex((x) => x === r), account: r })}>编辑</Button>
              <Button size="small" danger onClick={() => modal.confirm({ title: `移除账号 ${r.name}？`, content: "保存配置后生效；已上传对象不会被删除。", okText: "移除", okButtonProps: { danger: true }, onOk: () => commit(accounts.filter((a) => a !== r)) })}>移除</Button>
            </Space>
          ) },
        ]}
      />
      {editing && (
        <R2AccountModal
          open
          initial={editing.account}
          onCancel={() => setEditing(null)}
          onOk={(a) => {
            if (editing.index === null) {
              const next = [...accounts, a];
              commit(next);
              pager.setPage(Math.max(1, Math.ceil(next.length / pager.pageSize)));
            } else {
              commit(accounts.map((x, i) => (i === editing.index ? a : x)));
            }
            setEditing(null);
          }}
        />
      )}
    </>
  );
}

export default function Config() {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const [form] = Form.useForm<SystemConfig>();
  const query = useQuery({ queryKey: ["admin", "config"], queryFn: api.config });
  // R2 账号在弹窗里增删改，不走 ProForm 字段；保存时随表单一起提交
  const [r2Accounts, setR2Accounts] = useState<R2Account[] | null>(null);
  const [r2Dirty, setR2Dirty] = useState(false);
  const save = useMutation({
    mutationFn: api.saveConfig,
    onSuccess: (v) => {
      const prevSticky = form.getFieldValue(["proxy", "sticky_minutes"]);
      qc.setQueryData(["admin", "config"], v);
      qc.invalidateQueries({ queryKey: ["admin", "r2-usage"] });
      qc.invalidateQueries({ queryKey: ["announcement"] });
      form.setFieldValue(["proxy", "password"], undefined);
      form.setFieldValue("cloakbrowser_license_key", undefined);
      form.setFieldValue("cloakbrowser_license_key_masked", v.cloakbrowser_license_key_masked);
      if (v.proxy?.sticky_minutes != null) form.setFieldValue(["proxy", "sticky_minutes"], v.proxy.sticky_minutes);
      setR2Accounts(null); setR2Dirty(false);
      if (v.proxy?.sticky_minutes != null && prevSticky != null && v.proxy.sticky_minutes !== prevSticky) {
        message.success(`配置已保存；粘性会话已调到 ${v.proxy.sticky_minutes} 分钟（必须长过票 TTL）`);
      } else {
        message.success("配置已保存");
      }
    },
  });

  if (!query.data) return <Page title="系统配置" loading />;
  const cfg = query.data;
  const accounts = r2Accounts ?? cfg.r2_accounts;

  return (
    <Page title="系统配置" subtitle="通用、代理、上游调度、存储与计费">
      <div className="tab-panel">
        <ProForm<SystemConfig>
          form={form}
          initialValues={cfg}
          onReset={() => { setR2Accounts(null); setR2Dirty(false); }}
          onFinish={async (v) => { await save.mutateAsync({ ...cfg, ...v, proxy: { ...cfg.proxy, ...v.proxy }, r2_accounts: accounts }); }}
          submitter={{
            render: (_p, dom) => (
              <div className="cfg-actions">
                {r2Dirty && <Typography.Text type="warning" style={{ marginRight: "auto", fontSize: 12 }}>R2 账号有未保存的改动</Typography.Text>}
                <Space>{dom}</Space>
              </div>
            ),
            searchConfig: { submitText: "保存配置", resetText: "重置" },
            submitButtonProps: { icon: <SaveOutlined />, loading: save.isPending },
          }}
        >
          <Tabs className="compact-tabs" items={[
            { key: "general", label: "通用", children: (
              <div className="cfg-pane">
                <Section title="平台" desc="公告与接口等待策略">
                  <Row gutter={16}>
                    <Col xs={24} lg={12}><ProFormText name="announcement" label="平台公告" fieldProps={{ showCount: true, maxLength: 160 }} /></Col>
                    <Col xs={12} lg={6}><ProFormDigit name="sync_timeout_seconds" label="同步接口最长等待（秒）" min={10} max={600} extra="超时返回 504 + task_id，任务继续执行" /></Col>
                    <Col xs={12} lg={6}><ProFormDigit name="generation_timeout_seconds" label="单任务生成超时（秒）" min={30} max={1800} extra="worker 轮询上游超过则判失败并按容错策略重试" /></Col>
                  </Row>
                </Section>
                <Section title="用户默认配额" desc="新用户初始值；可在用户管理里单独覆盖">
                  <Row gutter={16}>
                    <Col xs={12} lg={6}><ProFormDigit name="default_rate_limit" label="默认限流（次/分钟）" min={1} max={10000} extra="超出返回 429" /></Col>
                    <Col xs={12} lg={6}><ProFormDigit name="user_concurrency_default" label="默认并发上限（任务数）" min={1} max={200} extra="用户同时 queued+running 任务数，最高 200。单号并发看「重试与容错」" /></Col>
                  </Row>
                </Section>
              </div>
            ) },
            { key: "proxy", label: "代理", children: <ProxyPane form={form} /> },
            { key: "upstream", label: "上游调度", children: (
              <div className="cfg-pane">
                <Section title="铸币工厂" desc="CloakBrowser PRO · Chrome 148。1–2 路热浏览器铸小池，提交 round-robin 取票。不要堆浏览器。">
                  <FactoryWatchdog />
                  <Row gutter={16}>
                    <Col xs={12} lg={4}><ProFormDigit name="mint_browser_count" label="浏览器数" min={1} max={8} extra="热进程路数，不是票数。20 并发 1–2 路够，不要堆浏览器" /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="mint_interval_seconds" label="每轮铸完空闲（秒）" min={1} max={300} extra="一轮 BATCH 之后再等。必须小于 TTL，建议约 10s" /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="arp_ttl_seconds" label="铸币票 TTL（秒）" min={30} max={600} extra="单位秒。5 分钟填 300。粘性会话必须再长 1 分钟，保存时不够会自动上调" /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="arp_max_uses" label="单票最大使用次数" min={1} max={10} extra="一枚可服务多账号；提交 round-robin 摊开，禁止压在同一枚上" /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="arp_min_ready" label="最低安全水位（枚）" min={1} extra="低于则马上再铸一批，不等空闲" /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="arp_pool_target" label="常备池目标（枚）" min={4} max={20} extra="满则停铸。20 并发靠这几枚新鲜票轮询，不是 20 个浏览器" /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="arp_mint_batch" label="每轮铸几枚" min={1} max={20} extra="每个热 worker 一轮 BATCH，各带独立住宅出口" /></Col>
                    <Col xs={24} lg={4}>
                      <ProFormText.Password
                        name="cloakbrowser_license_key"
                        label={<span>CloakBrowser License Key {cfg.cloakbrowser_license_key_masked && <Pill color="success">已配置</Pill>}</span>}
                        extra="开源 fingerprint-chromium 铸票不需要此项"
                        placeholder={cfg.cloakbrowser_license_key_masked ? `${cfg.cloakbrowser_license_key_masked} · 留空保持` : "cb_…"}
                        fieldProps={{ autoComplete: "new-password" }}
                      />
                    </Col>
                  </Row>
                </Section>
                <Section title="重试与容错" desc="账号调度、退避与可重试错误语义">
                  <Row gutter={16}>
                    <Col xs={12} lg={4}><ProFormSwitch name="adobe_dual_identity_enabled" label="非 2.5 走 FF-iOS" extra="开启：香蕉 / Image 2 走移动端，仅 2.5 走网页 ARP。关闭：全部走网页 clio。账号不再分 Normal/Alpha" /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="normal_canary_account_id" label="移动端灰度账号 ID" min={0} extra="0=全池；非 2.5（FF-iOS）只调度这一号" /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="alpha_canary_account_id" label="网页 2.5 灰度账号 ID" min={0} extra="0=全池；2.5 只调度这一号" /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="alpha_retry_max_attempts" label="Alpha 408 尝试上限" min={1} max={6} /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="alpha_retry_delay_seconds" label="Alpha 重试间隔（秒）" min={0.2} max={10} fieldProps={{ step: 0.2, precision: 1 }} /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="retry_max_attempts" label="最大尝试次数" min={1} max={30} /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="retry_backoff_base_seconds" label="重试退避基数（秒）" min={0.05} max={10} fieldProps={{ step: 0.1, precision: 2 }} /></Col>
                    <Col xs={12} lg={4}><ProFormSelect name="token_rotation" label="Token 轮换策略" options={[{ value: "random", label: "Random（随机）" }, { value: "round_robin", label: "Round Robin（轮询）" }, { value: "least_used", label: "Least Used（最少使用）" }]} /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="account_park_seconds" label="首次 408 冷却（秒）" min={30} max={3600} extra="测试建议 300（5 分钟）。到期改回可用，但仍受下面三条约束" /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="account_park_second_seconds" label="第二次 408 冷却（秒）" min={30} max={7200} extra="测试建议 600（10 分钟）" /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="account_park_disable_seconds" label="连续 408 长休（秒）" min={120} max={86400} extra="第 3 次起，测试建议 1800（30 分钟），不要 6 小时" /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="account_park_disable_after" label="连续几次 408 进入长休" min={2} max={10} extra="默认第 3 次。成功出图会清零计数" /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="account_408_observe_seconds" label="冷却后观察（秒）" min={0} max={86400} extra="到期后这段时间单号只跑 1 路。0 关闭。成功出图结束观察" /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="account_408_block_after" label="几次 408 后隔离敏感模型" min={1} max={10} extra="默认 1 次。成功出图才解除，避免冷却完立刻压 2.5" /></Col>
                    <Col xs={24} lg={8}><ProFormText name="account_408_block_models" label="高风险号禁止的模型" extra="逗号分隔。有 408 计数时这些模型不领该号，先用其它模型探活" /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="arp_bad_window_count" label="坏窗口 408 次数" min={2} max={50} extra="窗口期内达到次数则降速" /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="arp_bad_window_seconds" label="坏窗口统计时长（秒）" min={10} max={600} extra="默认 60 秒" /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="arp_bad_window_pause_seconds" label="坏窗口降速（秒）" min={0} max={3600} extra="期间不再换号连打，单号只跑 1 路。0 关闭" /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="worker_concurrency" label="Worker 同时处理数" min={1} max={200} extra="进程内并行任务。要 200 路排队必须 ≥ 用户并发" /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="account_concurrency_normal" label="单号并发数（普通）" min={1} max={16} extra="实测安全值 4，再高易 408。全站并发 = 可用号 × 此值" /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="account_concurrency_advanced" label="单号并发数（4K/高级）" min={1} max={8} /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="account_daily_image_limit" label="普号每日出图上限" min={1} max={1000} /></Col>
                    <Col xs={12} lg={4}><ProFormDigit name="disabled_auto_enable_waterline" label="禁用号自动启用水位" min={0} max={100} /></Col>
                    <Col xs={12} lg={10}><ProFormText name="retryable_status_codes" label="可重试状态码" placeholder="429,451,500,502,503,422" extra="429/451 不冷却账号，按重试次数退避" /></Col>
                    <Col xs={24} lg={10}><ProFormText name="retryable_error_types" label="可重试错误类型" placeholder="UpstreamTemporaryError" /></Col>
                  </Row>
                </Section>
              </div>
            ) },
            { key: "storage", label: "存储", children: (
              <div className="cfg-pane">
                <Section title="存储后端" desc="决定生成的图片/视频如何存储与分发">
                  <Row gutter={16}>
                    <Col xs={24} lg={8}><ProFormSelect name="storage_backend" label="存储后端" options={[{ value: "r2", label: "Cloudflare R2（多账号 10GB×N）" }, { value: "s3", label: "Amazon S3" }, { value: "minio", label: "MinIO" }]} /></Col>
                    <Col xs={24} lg={8}><ProFormSelect name="gemini_image_response_format" label="Gemini 接口响应格式" extra="仅影响 Gemini 兼容接口 (v1beta) 的图片输出，不影响 OpenAI 接口" options={[{ value: "url", label: "URL（返回图片链接）" }, { value: "inline", label: "Inline（Base64）" }]} /></Col>
                  </Row>
                </Section>
                <Section title={`Cloudflare R2 账号（${accounts.length}）`} desc={
                  <>多账号 = 多份 10GB，同一账号再开 Access Key 不增加额度；上传按账号轮询，满额或禁用自动跳过。对象 1 天过期，10 × 10GB 按日均 25–35GB 有余量。public_base_url 填已生效的 r2.dev 或已绑定 DNS 的自定义域名。</>
                }>
                  <R2Panel accounts={accounts} onChange={(next) => { setR2Accounts(next); setR2Dirty(true); }} />
                </Section>
              </div>
            ) },
            { key: "pricing", label: "计费", children: (
              <div className="cfg-pane">
                <Section title="图片生成" desc="按输出分辨率等级扣费，生成成功后扣除；普通模型与 Pro 模型分别定价">
                  <div className="price-grid">
                    <div className="price-grid-head"><span>模型</span><span>1K</span><span>2K</span><span>4K</span></div>
                    {cfg.image_pricing.map((m, mi) => (
                      <div className="price-grid-row" key={m.model_id}>
                        <div className="price-model">
                          <span>{m.model_name}</span>
                          {m.model_note && <Typography.Text type="secondary" code style={{ fontSize: 11 }}>{m.model_note}</Typography.Text>}
                        </div>
                        {m.tiers.map((t, ti) => (
                          <div className="price-cell" key={t.resolution}>
                            <CreditInput name={["image_pricing", mi, "tiers", ti, "price"]} unit="积分/次" />
                            <span className="price-pixels">{t.pixels}</span>
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                </Section>
                <Section title="视频生成" desc="Omni / Seedance 按秒计费（费用 = 单价 × 时长），其余按次；仅成功后扣除">
                  <div className="price-grid price-grid-video">
                    <div className="price-grid-head"><span>模型</span><span>说明</span><span>计费</span><span>单价</span></div>
                    {cfg.video_pricing.map((m, mi) => (
                      <div className="price-grid-row" key={m.model_id}>
                        <div className="price-model">{m.model_name}</div>
                        <Typography.Text type="secondary">{m.note}</Typography.Text>
                        <div><Pill color={m.billing === "per_second" ? "purple" : "processing"}>{m.billing === "per_second" ? "按秒" : "按次"}</Pill></div>
                        <div className="price-cell"><CreditInput name={["video_pricing", mi, "price"]} unit={m.billing === "per_second" ? "积分/秒" : "积分/次"} /></div>
                      </div>
                    ))}
                  </div>
                </Section>
              </div>
            ) },
      ]} />
    </ProForm>
      </div>
    </Page>
  );
}
