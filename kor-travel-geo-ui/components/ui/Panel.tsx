export function Panel({
  title,
  children,
  actions
}: {
  title: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h2>{title}</h2>
        {actions}
      </div>
      <div className="panel-body">{children}</div>
    </section>
  );
}
