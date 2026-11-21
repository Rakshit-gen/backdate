export function PageHead({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="page-head">
      <h1>{title}</h1>
      <div className="lede">{children}</div>
    </div>
  );
}
