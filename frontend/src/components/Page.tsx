import { Spin } from "antd";
import { createContext, useContext, useEffect, type ReactNode } from "react";

export interface PageHeaderState { title?: ReactNode; subtitle?: ReactNode }

export const PageHeaderContext = createContext<((state: PageHeaderState) => void) | null>(null);

/**
 * 页面容器：标题/副标题上报到布局顶栏，工具按钮放在内容首行右侧。
 */
export function Page({ title, subtitle, extra, loading, children }: PageHeaderState & { extra?: ReactNode; loading?: boolean; children?: ReactNode }) {
  const setHeader = useContext(PageHeaderContext);
  useEffect(() => { setHeader?.({ title, subtitle }); }, [setHeader, title, subtitle]);
  if (loading) return <div className="page page-loading"><Spin /></div>;
  return (
    <div className="page">
      {extra && <div className="page-toolbar">{extra}</div>}
      {children}
    </div>
  );
}
