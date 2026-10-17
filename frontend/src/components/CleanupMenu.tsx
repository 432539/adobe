import { App, Button, Dropdown } from "antd";

export type CleanupScope = "failed" | "older_3d" | "all";

const LABELS: Record<CleanupScope, string> = {
  failed: "清理失败",
  older_3d: "清理三天前",
  all: "清理全部",
};

const HINTS: Record<CleanupScope, string> = {
  failed: "将删除失败记录，此操作不可恢复。",
  older_3d: "将删除三天前的记录，此操作不可恢复。",
  all: "将删除全部记录，此操作不可恢复。",
};

export function CleanupMenu({
  onClean,
  loading,
}: {
  onClean: (scope: CleanupScope) => Promise<number>;
  loading?: boolean;
}) {
  const { modal, message } = App.useApp();
  return (
    <Dropdown
      menu={{
        items: [
          { key: "failed", label: LABELS.failed },
          { key: "older_3d", label: LABELS.older_3d },
          { key: "all", label: LABELS.all, danger: true },
        ],
        onClick: ({ key }) => {
          const scope = key as CleanupScope;
          modal.confirm({
            title: LABELS[scope],
            content: HINTS[scope],
            okButtonProps: { danger: scope === "all" },
            onOk: async () => {
              const deleted = await onClean(scope);
              message.success(`已清理 ${deleted} 条`);
            },
          });
        },
      }}
    >
      <Button loading={loading}>清理</Button>
    </Dropdown>
  );
}
