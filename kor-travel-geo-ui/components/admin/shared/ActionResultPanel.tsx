import { Panel } from "@/components/ui/Panel";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { EmptyState } from "@/components/admin/shared/EmptyState";

/**
 * 액션의 '최근 결과' 표준 패널. 즉시 피드백은 toast가 담당하고, 이 패널은
 * 마지막 응답의 상세 확인용으로 남는다. mock spec들이 pre 내용을 어서션하므로
 * JSON은 항상 펼친 상태로 렌더한다.
 */
export function ActionResultPanel({
  result,
  title = "최근 결과",
  emptyHint = "아직 실행한 작업이 없습니다.",
  actions
}: {
  result: unknown;
  title?: string;
  emptyHint?: string;
  actions?: React.ReactNode;
}) {
  return (
    <Panel title={title} actions={actions}>
      {result == null ? <EmptyState>{emptyHint}</EmptyState> : <JsonBlock value={result} />}
    </Panel>
  );
}
