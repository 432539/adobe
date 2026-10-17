import {
  BarChartOutlined, BookOutlined, BulbOutlined, CodeOutlined, HistoryOutlined,
  KeyOutlined, LogoutOutlined, MenuFoldOutlined, MenuUnfoldOutlined, MoonOutlined,
  SafetyCertificateOutlined, SettingOutlined, TeamOutlined, ThunderboltOutlined, TransactionOutlined,
  UserOutlined, WalletOutlined,
} from "@ant-design/icons";
import { ProLayout, type MenuDataItem } from "@ant-design/pro-components";
import { Avatar, Button, Dropdown, Tooltip } from "antd";
import { useCallback, useMemo, useState } from "react";
import { Link, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { AnnouncementBell } from "@/components/AnnouncementBell";
import { PageHeaderContext, type PageHeaderState } from "@/components/Page";
import { useAuth, useUi } from "@/store/auth";
import { OSS_REPO_URL, SUPPORT_QQ_GROUP, SUPPORT_QQ_LABEL } from "@/constants/support";
import { fmtCredits } from "@/utils/format";

const userRoutes: MenuDataItem[] = [
  { name: "创作", children: [
    { path: "/create", name: "创作中心", icon: <ThunderboltOutlined /> },
    { path: "/history", name: "生成历史", icon: <HistoryOutlined /> },
    { path: "/keys", name: "KEY 管理", icon: <KeyOutlined /> },
    { path: "/docs", name: "调用说明", icon: <BookOutlined /> },
  ] },
  { name: "账户", children: [
    { path: "/billing", name: "余额明细", icon: <WalletOutlined /> },
    { path: "/settings", name: "个人设置", icon: <SettingOutlined /> },
  ] },
];
const adminRoutes: MenuDataItem[] = [
  { name: "运营", children: [
    { path: "/admin/dashboard", name: "系统总览", icon: <BarChartOutlined /> },
    { path: "/admin/users", name: "用户管理", icon: <UserOutlined /> },
    { path: "/admin/accounts", name: "号池管理", icon: <TeamOutlined /> },
    { path: "/admin/records", name: "财务记录", icon: <TransactionOutlined /> },
    { path: "/admin/logs", name: "请求日志", icon: <CodeOutlined /> },
  ] },
  { name: "系统", children: [
    { path: "/admin/minting", name: "铸票系统", icon: <SafetyCertificateOutlined /> },
    { path: "/admin/config", name: "系统配置", icon: <SettingOutlined /> },
  ] },
];

export function AppLayout() {
  const { token, profile, logout } = useAuth();
  const { dark, toggleDark, collapsed, setCollapsed } = useUi();
  const location = useLocation();
  const navigate = useNavigate();
  // 管理员同时拥有用户功能；普通用户看不到管理菜单
  const routes = useMemo(() => profile?.role === "admin" ? [...adminRoutes, ...userRoutes] : userRoutes, [profile?.role]);
  const [header, setHeaderState] = useState<PageHeaderState>({});
  const setHeader = useCallback((state: PageHeaderState) => setHeaderState(state), []);
  const siderBg = dark ? "#0b1220" : "#0d1b4c";

  if (!token || !profile) return <Navigate to="/login" state={{ from: location.pathname }} replace />;

  return (
    <PageHeaderContext.Provider value={setHeader}>
      <ProLayout
        className="app-layout"
        layout="side"
        navTheme="light"
        headerRender={false}
        fixSiderbar
        collapsed={collapsed}
        onCollapse={setCollapsed}
        breakpoint="lg"
        siderWidth={208}
        contentWidth="Fluid"
        route={{ path: "/", routes }}
        location={{ pathname: location.pathname }}
        menu={{ locale: false, type: "group" }}
        menuItemRender={(item, dom) => item.path ? <Link to={item.path}>{dom}</Link> : dom}
        menuHeaderRender={() => (
          <div className="brand" onClick={() => navigate(profile.role === "admin" ? "/admin/dashboard" : "/create")}>
            <div className="brand-logo">AD</div>
            {!collapsed && <div className="brand-text"><div className="brand-name">AD小怪兽</div><div className="brand-sub">CONSOLE</div></div>}
          </div>
        )}
        menuFooterRender={(props) => props?.collapsed ? null : (
          <div className="sider-foot">
            <div>技术：闲的无聊</div>
            <div><a href={OSS_REPO_URL} target="_blank" rel="noreferrer" style={{ color: "inherit" }}>开源 {OSS_REPO_URL.replace("https://", "")}</a></div>
            <div>{SUPPORT_QQ_LABEL}</div>
            <div>QQ 群 {SUPPORT_QQ_GROUP}</div>
          </div>
        )}
        collapsedButtonRender={false}
        contentStyle={{ padding: 0 }}
        token={{
          sider: {
            colorMenuBackground: siderBg,
            colorTextMenu: "rgba(255,255,255,.72)",
            colorTextMenuSecondary: "rgba(255,255,255,.4)",
            colorTextMenuTitle: "#fff",
            colorTextMenuSelected: "#fff",
            colorTextMenuActive: "#fff",
            colorTextMenuItemHover: "#fff",
            colorBgMenuItemSelected: "#1d2f6b",
            colorBgMenuItemHover: "rgba(255,255,255,.06)",
            colorMenuItemDivider: "rgba(255,255,255,.08)",
            paddingBlockLayoutMenu: 8,
            paddingInlineLayoutMenu: 8,
          },
        }}
      >
        <header className="top-bar">
          <div className="page-head">
            <Button className="header-action" type="text" icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />} onClick={() => setCollapsed(!collapsed)} />
            <div>
              <div className="page-head-title">{header.title}</div>
              {header.subtitle && <div className="page-head-sub">{header.subtitle}</div>}
            </div>
          </div>
          <div className="top-bar-actions">
            <span className="status-chip"><span className="status-dot" />系统运行中</span>
            {profile.role === "user" && <span className="status-chip status-chip-blue"><WalletOutlined /> 余额 {fmtCredits(profile.balance)}</span>}
            <Tooltip title={dark ? "浅色主题" : "深色主题"}><Button className="header-action" type="text" icon={dark ? <BulbOutlined /> : <MoonOutlined />} onClick={toggleDark} /></Tooltip>
            <AnnouncementBell />
            <Dropdown menu={{ items: [
              { key: "role", label: profile.role === "admin" ? "管理员" : "普通用户", disabled: true },
              { type: "divider" },
              { key: "logout", label: "退出登录", icon: <LogoutOutlined />, danger: true, onClick: () => { logout(); navigate("/login"); } },
            ] }}>
              <span className="user-chip"><Avatar size={26} style={{ background: "#2f54eb" }}>{profile.username.slice(0, 1)}</Avatar><span className="user-chip-name">{profile.username}</span></span>
            </Dropdown>
          </div>
        </header>
        <Outlet />
      </ProLayout>
    </PageHeaderContext.Provider>
  );
}
