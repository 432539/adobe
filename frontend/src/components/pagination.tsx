import { InputNumber, type TablePaginationConfig } from "antd";
import { useCallback, useState } from "react";

export const PAGE_SIZE_DEFAULT = 10;

export interface Pager {
  page: number;
  pageSize: number;
  setPage: (page: number) => void;
  /** Unified table pagination: first/last page, editable page size, total hint */
  pagination: (total?: number) => TablePaginationConfig;
}

export function usePager(defaultPageSize = PAGE_SIZE_DEFAULT): Pager {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(defaultPageSize);

  const pagination = useCallback((total = 0): TablePaginationConfig => {
    const pages = Math.max(1, Math.ceil(total / pageSize));
    const go = (next: number) => setPage(Math.min(Math.max(1, next), pages));
    const applySize = (raw: string | number | null) => {
      const next = Math.floor(Number(raw));
      if (!Number.isFinite(next) || next < 1 || next === pageSize) return;
      setPageSize(Math.min(next, 200));
      setPage(1);
    };
    return {
      current: page,
      pageSize,
      total,
      size: "default",
      showSizeChanger: false,
      showLessItems: false,
      onChange: (next) => setPage(next),
      showTotal: (count) => (
        <span className="pager-total">
          {"\u5171"} {count} {"\u6761"} {"\u00b7"} {"\u6bcf\u9875"}
          <InputNumber
            key={pageSize}
            size="middle"
            className="pager-size"
            min={1}
            max={200}
            precision={0}
            controls={false}
            defaultValue={pageSize}
            onBlur={(e) => applySize(e.target.value)}
            onPressEnter={(e) => applySize((e.target as HTMLInputElement).value)}
          />
          {"\u6761"}
        </span>
      ),
      itemRender: (_page, type, element) => {
        if (type === "prev") {
          return (
            <span className="pager-edge">
              <button type="button" className="pager-btn" disabled={page <= 1} onClick={(e) => { e.stopPropagation(); go(1); }}>{"\u9996\u9875"}</button>
              {element}
            </span>
          );
        }
        if (type === "next") {
          return (
            <span className="pager-edge">
              {element}
              <button type="button" className="pager-btn" disabled={page >= pages} onClick={(e) => { e.stopPropagation(); go(pages); }}>{"\u5c3e\u9875"}</button>
            </span>
          );
        }
        return element;
      },
    };
  }, [page, pageSize]);

  return { page, pageSize, setPage, pagination };
}