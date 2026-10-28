export interface InfoItem {
  label: string
  value: string
}

export function InfoCard({ title, items }: { title: string; items: InfoItem[] }) {
  return (
    <section className="analysis-info-card">
      <h2>{title}</h2>
      <div className="analysis-info-grid">
        {items.map((item) => (
          <div key={item.label}>
            <span>{item.label}</span>
            <strong>{item.value || '—'}</strong>
          </div>
        ))}
      </div>
    </section>
  )
}
