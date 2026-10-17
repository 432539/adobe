import { Component, lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Alert, Button, Result, Spin } from "antd";
import { AppLayout } from "@/layouts/AppLayout";
import { useAuth } from "@/store/auth";

const Login = lazy(() => import("@/pages/Login"));
const Create = lazy(() => import("@/pages/user/Create"));
const History = lazy(() => import("@/pages/user/History"));
const Keys = lazy(() => import("@/pages/user/Keys"));
const Docs = lazy(() => import("@/pages/user/Docs"));
const Billing = lazy(() => import("@/pages/user/Billing"));
const Settings = lazy(() => import("@/pages/user/Settings"));
const Dashboard = lazy(() => import("@/pages/admin/Dashboard"));
const Users = lazy(() => import("@/pages/admin/Users"));
const Ledger = lazy(() => import("@/pages/admin/Ledger"));
const Config = lazy(() => import("@/pages/admin/Config"));
const Minting = lazy(() => import("@/pages/admin/Minting"));
const Logs = lazy(() => import("@/pages/admin/Logs"));
const Accounts = lazy(() => import("@/pages/admin/Accounts"));

class RouteErrorBoundary extends Component<{ children: ReactNode }, { error?: Error }> {
  state: { error?: Error } = {};

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (!this.state.error) return this.props.children;
    return <Result status="error" title="页面加载失败" subTitle="页面组件出现异常，请刷新后重试。" extra={<Button type="primary" onClick={() => location.reload()}>刷新页面</Button>}><Alert type="error" message="若问题持续存在，请联系管理员并提供当前时间。" /></Result>;
  }
}

function Home() {
  const profile = useAuth((state) => state.profile);
  return <Navigate to={profile?.role === "admin" ? "/admin/dashboard" : "/create"} replace />;
}

/** 管理员可访问全部页面；普通用户只能访问用户页面 */
function RoleRoute({ role, children }: { role: "admin" | "user"; children: React.ReactNode }) {
  const profile = useAuth((state) => state.profile);
  if (!profile) return <Navigate to="/login" replace />;
  if (role === "admin" && profile.role !== "admin") return <Home />;
  return children;
}

const fallback = <div className="route-loading"><Spin size="large" /></div>;

export default function App() {
  return (
    <Suspense fallback={fallback}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<AppLayout />}>
          <Route index element={<Home />} />
          <Route path="create" element={<RoleRoute role="user"><RouteErrorBoundary><Create /></RouteErrorBoundary></RoleRoute>} />
          <Route path="history" element={<RoleRoute role="user"><History /></RoleRoute>} />
          <Route path="keys" element={<RoleRoute role="user"><Keys /></RoleRoute>} />
          <Route path="docs" element={<RoleRoute role="user"><Docs /></RoleRoute>} />
          <Route path="billing" element={<RoleRoute role="user"><Billing /></RoleRoute>} />
          <Route path="settings" element={<RoleRoute role="user"><Settings /></RoleRoute>} />
          <Route path="admin/dashboard" element={<RoleRoute role="admin"><Dashboard /></RoleRoute>} />
          <Route path="admin/users" element={<RoleRoute role="admin"><Users /></RoleRoute>} />
          <Route path="admin/accounts" element={<RoleRoute role="admin"><Accounts /></RoleRoute>} />
          <Route path="admin/records" element={<RoleRoute role="admin"><Ledger /></RoleRoute>} />
          <Route path="admin/config" element={<RoleRoute role="admin"><Config /></RoleRoute>} />
          <Route path="admin/minting" element={<RoleRoute role="admin"><Minting /></RoleRoute>} />
          <Route path="admin/logs" element={<RoleRoute role="admin"><Logs /></RoleRoute>} />
        </Route>
        <Route path="*" element={<Home />} />
      </Routes>
    </Suspense>
  );
}
