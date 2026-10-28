import { Icon } from '@/shared/icons/Icon'

export function PatientPagination({
  total,
  page,
  pageCount,
  pageSize,
  onPage,
}: {
  total: number
  page: number
  pageCount: number
  pageSize: number
  onPage: (page: number) => void
}) {
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1
  const end = Math.min(page * pageSize, total)

  return (
    <div className="table-footer">
      <span>
        Showing {start}–{end} of {total} patients
      </span>
      <div className="pagination">
        <button
          type="button"
          onClick={() => onPage(Math.max(1, page - 1))}
          disabled={page === 1}
          aria-label="Previous page"
        >
          <Icon name="chevron-left" size={13} />
        </button>
        {Array.from({ length: pageCount }, (_, index) => index + 1)
          .slice(Math.max(0, page - 3), Math.max(0, page - 3) + 5)
          .map((number) => (
            <button
              type="button"
              key={number}
              aria-current={number === page ? 'page' : undefined}
              onClick={() => onPage(number)}
            >
              {number}
            </button>
          ))}
        <button
          type="button"
          onClick={() => onPage(Math.min(pageCount, page + 1))}
          disabled={page === pageCount}
          aria-label="Next page"
        >
          <Icon name="chevron-right" size={13} />
        </button>
      </div>
    </div>
  )
}
