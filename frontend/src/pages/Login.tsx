import { CloudServerOutlined, LockOutlined, UserOutlined } from "@ant-design/icons";
import { ProForm, ProFormText } from "@ant-design/pro-components";
import { App, Card, Flex, Typography } from "antd";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { OSS_REPO_LABEL, OSS_REPO_URL, SUPPORT_QQ_GROUP, SUPPORT_QQ_LABEL } from "@/constants/support";
import { api } from "@/services/api";
import { useAuth } from "@/store/auth";

interface LoginValues { username: string; password: string }

export default function Login() {
  const [loading, setLoading] = useState(false);
  const { message } = App.useApp();
  const setSession = useAuth((s) => s.setSession);
  const navigate = useNavigate();
  const location = useLocation();

  const submit = async (values: LoginValues) => {
    setLoading(true);
    try {
      const session = await api.login(values.username, values.password);
      setSession(session.token, session.profile);
      message.success("登录成功");
      const wanted = (location.state as { from?: string } | null)?.from;
      navigate(wanted || (session.role === "admin" ? "/admin/dashboard" : "/create"), { replace: true });
    } catch (e) {
      message.error(e instanceof Error ? e.message : "登录失败");
    } finally { setLoading(false); }
  };

  return (
    <div className="login-bg">
      <Card style={{ width: "min(100%, 400px)" }} styles={{ body: { padding: 32 } }}>
        <Flex align="center" gap={12} style={{ marginBottom: 24 }}>
          <Flex align="center" justify="center" style={{ width: 40, height: 40, borderRadius: 8, background: "#2f54eb", color: "#fff", fontSize: 20 }}><CloudServerOutlined /></Flex>
          <div>
            <Typography.Title level={4} style={{ margin: 0, fontWeight: 400 }}>AD小怪兽</Typography.Title>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>生图 / 生视频中转控制台</Typography.Text>
          </div>
        </Flex>
        <ProForm<LoginValues>
          submitter={{ searchConfig: { submitText: "登录" }, submitButtonProps: { block: true, loading }, resetButtonProps: { style: { display: "none" } } }}
          initialValues={{ username: "admin", password: "" }}
          onFinish={submit}
        >
          <ProFormText name="username" fieldProps={{ prefix: <UserOutlined />, autoComplete: "username" }} placeholder="用户名或邮箱" rules={[{ required: true, message: "请输入用户名" }]} />
          <ProFormText.Password name="password" fieldProps={{ prefix: <LockOutlined />, autoComplete: "current-password" }} placeholder="密码" rules={[{ required: true, message: "请输入密码" }]} />
        </ProForm>
        <Typography.Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0, textAlign: "center" }}>
          {OSS_REPO_LABEL}{" "}
          <Typography.Link href={OSS_REPO_URL} target="_blank" rel="noreferrer">{OSS_REPO_URL}</Typography.Link>
          <br />
          {SUPPORT_QQ_LABEL}（{SUPPORT_QQ_GROUP}）
        </Typography.Paragraph>
      </Card>
    </div>
  );
}
