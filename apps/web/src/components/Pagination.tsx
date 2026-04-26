interface Props {
  page: number;
  totalPages: number;
  onChange: (p: number) => void;
}

export default function Pagination({ page, totalPages, onChange }: Props) {
  if (totalPages <= 1) return null;
  const max = Math.min(7, totalPages);
  const start = Math.max(1, Math.min(page - 3, totalPages - max + 1));

  return (
    <div className="flex justify-center gap-1 mt-4">
      <button
        className="px-3 py-1.5 border border-gray-300 rounded text-sm disabled:opacity-50"
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
      >
        ← Prev
      </button>
      {Array.from({ length: max }, (_, i) => start + i).map((p) => (
        <button
          key={p}
          className={`px-3 py-1.5 border rounded text-sm ${
            p === page
              ? "bg-tg-primary text-white border-tg-primary"
              : "border-gray-300 hover:bg-gray-50"
          }`}
          onClick={() => onChange(p)}
        >
          {p}
        </button>
      ))}
      <button
        className="px-3 py-1.5 border border-gray-300 rounded text-sm disabled:opacity-50"
        disabled={page >= totalPages}
        onClick={() => onChange(page + 1)}
      >
        Next →
      </button>
    </div>
  );
}
