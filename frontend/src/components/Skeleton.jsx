export function SkeletonText({ width = 'medium' }) {
  return <div className={`skeleton skeleton-text ${width}`} />
}

export function SkeletonCard() {
  return <div className="card skeleton skeleton-card" />
}

export function BreakCardSkeleton() {
  return (
    <div className="break-card">
      <SkeletonText width="medium" />
      <SkeletonText width="short" />
      <div style={{ marginTop: 12 }}>
        <SkeletonText width="short" />
      </div>
    </div>
  )
}

export function BreakDetailSkeleton() {
  return (
    <div className="break-details animate-fade-in">
      <div className="card">
        <SkeletonText width="medium" />
        <div style={{ height: 16 }} />
        <SkeletonText width="long" />
        <SkeletonText width="long" />
        <SkeletonText width="medium" />
        <div style={{ height: 24 }} />
        <div className="details-grid">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="detail-item">
              <SkeletonText width="short" />
              <SkeletonText width="medium" />
            </div>
          ))}
        </div>
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <SkeletonText width="short" />
        <div style={{ height: 16 }} />
        <div className="conditions-grid">
          {[1, 2, 3].map(i => (
            <div key={i} className="condition-item">
              <SkeletonText width="short" />
              <SkeletonText width="medium" />
            </div>
          ))}
        </div>
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <SkeletonText width="short" />
        <div style={{ height: 140 }} className="skeleton" />
      </div>
    </div>
  )
}
