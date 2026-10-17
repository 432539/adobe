import { BellOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Badge, Button, Empty, Popover, Spin } from "antd";
import { useCallback, useState } from "react";
import { api } from "@/services/api";

const SEEN_KEY = "ff.announcement.seen";

function readSeen(): string {
  try {
    return localStorage.getItem(SEEN_KEY) ?? "";
  } catch {
    return "";
  }
}

function writeSeen(text: string) {
  try {
    localStorage.setItem(SEEN_KEY, text);
  } catch {
    /* private mode */
  }
}

export function AnnouncementBell() {
  const query = useQuery({
    queryKey: ["announcement"],
    queryFn: api.announcement,
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
  const text = (query.data?.announcement ?? "").trim();
  const [seen, setSeen] = useState(readSeen);
  const unread = Boolean(text) && seen !== text;

  const onOpenChange = useCallback((open: boolean) => {
    if (!open || !text) return;
    writeSeen(text);
    setSeen(text);
  }, [text]);

  const body = query.isLoading ? (
    <div className="announce-empty"><Spin size="small" /></div>
  ) : text ? (
    <div className="announce-body">{text}</div>
  ) : (
    <Empty className="announce-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无平台公告" />
  );

  return (
    <Popover
      trigger="click"
      placement="bottomRight"
      title="平台公告"
      overlayClassName="announce-pop"
      onOpenChange={onOpenChange}
      content={body}
    >
      <span>
        <Badge dot={unread} offset={[-6, 6]}>
          <Button className="header-action" type="text" icon={<BellOutlined />} aria-label="平台公告" />
        </Badge>
      </span>
    </Popover>
  );
}
