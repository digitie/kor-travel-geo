export function PageHeader({
  title,
  description,
  actions
}: {
  title: string;
  /** 선택 — 정말 필요한 한 줄만. 탭/패널 제목과 중복되면 생략한다. */
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <header className="page-head">
      <div className="page-title">
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {actions}
    </header>
  );
}
