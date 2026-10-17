import { LockOutlined, SaveOutlined, UserOutlined } from "@ant-design/icons";
import { ProForm, ProFormSwitch, ProFormText } from "@ant-design/pro-components";
import { App, Avatar, Col, Row, Space, Tabs, Typography } from "antd";
import type { ReactNode } from "react";
import { Page } from "@/components/Page";
import { Pill } from "@/components/ui";
import { useAuth } from "@/store/auth";
import { OSS_REPO_LABEL, OSS_REPO_URL, SUPPORT_QQ_GROUP, SUPPORT_QQ_LABEL } from "@/constants/support";
import { fmtCredits, fmtTime } from "@/utils/format";

const submitter = (text: string) => ({
  render: (_p: unknown, dom: ReactNode[]) => <div className="cfg-actions"><Space>{dom}</Space></div>,
  searchConfig: { submitText: text, resetText: "重置" },
  submitButtonProps: { icon: <SaveOutlined /> },
});

export default function Settings() {
  const profile = useAuth((s) => s.profile);
  const { message } = App.useApp();

  return (
    <Page title="个人设置" subtitle="资料、安全与通知偏好">
      <div className="tab-panel">
        <div className="profile-head">
          <Avatar size={56} style={{ background: "#2f54eb", flex: "none" }} icon={<UserOutlined />} />
          <div className="profile-meta">
            <div className="profile-name">
              {profile?.username}
              <Pill color={profile?.role === "admin" ? "purple" : "processing"}>{profile?.role === "admin" ? "管理员" : "用户"}</Pill>
            </div>
            <div className="profile-sub">{profile?.email}</div>
          </div>
          <div className="profile-facts">
            <div><span className="profile-fact-k">余额</span><span className="tnum">{fmtCredits(profile?.balance ?? 0)} 积分</span></div>
            <div><span className="profile-fact-k">注册时间</span><span className="tnum">{fmtTime(profile?.created_at)}</span></div>
            <div><span className="profile-fact-k">上次登录</span><span className="tnum">{fmtTime(profile?.last_login_at)}</span></div>
          </div>
        </div>

        <Tabs className="compact-tabs" items={[
          { key: "profile", label: "基本资料", children: (
            <ProForm initialValues={profile ?? {}} submitter={submitter("保存资料")} onFinish={async () => { message.success("资料已保存"); return true; }}>
              <div className="cfg-pane">
                <section className="cfg-section">
                  <div className="cfg-section-head"><div><div className="cfg-section-title">账户资料</div><div className="cfg-section-desc">昵称用于面板展示；邮箱作为登录凭据，如需更换请联系管理员</div></div></div>
                  <Row gutter={16}>
                    <Col xs={24} md={8}><ProFormText name="username" label="昵称" rules={[{ required: true, message: "必填" }, { max: 32 }]} /></Col>
                    <Col xs={24} md={8}><ProFormText name="email" label="邮箱" disabled /></Col>
                  </Row>
                </section>
              </div>
            </ProForm>
          ) },
          { key: "security", label: "安全设置", children: (
            <ProForm submitter={submitter("更新密码")} onFinish={async () => { message.success("密码已更新"); return true; }}>
              <div className="cfg-pane">
                <section className="cfg-section">
                  <div className="cfg-section-head"><div><div className="cfg-section-title">修改密码</div><div className="cfg-section-desc">至少 8 位；修改后其他设备需重新登录，已签发的 API KEY 不受影响</div></div></div>
                  <Row gutter={16}>
                    <Col xs={24} md={8}><ProFormText.Password name="old" label="当前密码" fieldProps={{ prefix: <LockOutlined />, autoComplete: "current-password" }} rules={[{ required: true, message: "必填" }]} /></Col>
                    <Col xs={24} md={8}><ProFormText.Password name="next" label="新密码" fieldProps={{ autoComplete: "new-password" }} rules={[{ required: true, message: "必填" }, { min: 8, message: "至少 8 位" }]} /></Col>
                    <Col xs={24} md={8}>
                      <ProFormText.Password
                        name="confirm"
                        label="确认新密码"
                        dependencies={["next"]}
                        fieldProps={{ autoComplete: "new-password" }}
                        rules={[{ required: true, message: "必填" }, ({ getFieldValue }) => ({ validator: (_, v) => (!v || v === getFieldValue("next") ? Promise.resolve() : Promise.reject(new Error("两次输入不一致"))) })]}
                      />
                    </Col>
                  </Row>
                </section>
              </div>
            </ProForm>
          ) },
          { key: "notify", label: "通知", children: (
            <ProForm initialValues={{ job_notice: true, balance_notice: true, key_notice: true }} submitter={submitter("保存偏好")} onFinish={async () => { message.success("通知偏好已保存"); return true; }}>
              <div className="cfg-pane">
                <section className="cfg-section">
                  <div className="cfg-section-head"><div><div className="cfg-section-title">通知偏好</div><div className="cfg-section-desc">通过站内消息与邮箱送达</div></div></div>
                  <div className="pref-list">
                    <div className="pref-row"><div><div>任务完成通知</div><div className="cfg-section-desc">生成成功或失败时提醒</div></div><ProFormSwitch name="job_notice" noStyle /></div>
                    <div className="pref-row"><div><div>余额不足提醒</div><div className="cfg-section-desc">余额低于 10 积分时提醒</div></div><ProFormSwitch name="balance_notice" noStyle /></div>
                    <div className="pref-row"><div><div>KEY 安全事件</div><div className="cfg-section-desc">KEY 创建、吊销或异常调用</div></div><ProFormSwitch name="key_notice" noStyle /></div>
                  </div>
                </section>
              </div>
            </ProForm>
          ) },
          { key: "support", label: "技术支持", children: (
            <div className="cfg-pane">
              <section className="cfg-section">
                <div className="cfg-section-head">
                  <div>
                    <div className="cfg-section-title">开源与技术支持</div>
                    <div className="cfg-section-desc">源码公开；平台使用、对接 API、出图异常请加群，地址和群号可复制</div>
                  </div>
                </div>
                <Typography.Paragraph copyable={{ text: OSS_REPO_URL }} style={{ marginBottom: 8 }}>
                  {OSS_REPO_LABEL}：<Typography.Link href={OSS_REPO_URL} target="_blank" rel="noreferrer">{OSS_REPO_URL}</Typography.Link>
                </Typography.Paragraph>
                <div className="cfg-section-title" style={{ marginBottom: 8 }}>{SUPPORT_QQ_LABEL}</div>
                <Typography.Text copyable style={{ fontSize: 18 }}>{SUPPORT_QQ_GROUP}</Typography.Text>
              </section>
            </div>
          ) },
        ]} />
      </div>
    </Page>
  );
}
