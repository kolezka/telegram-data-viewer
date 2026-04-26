import { useEffect, useState } from "react";

interface Props {
  page: number;
  totalPages: number;
  onChange: (p: number) => void;
}

export default function Pagination({ page, totalPages, onChange }: Props) {
  const [jumpInput, setJumpInput] = useState(String(page));

  // Keep the input in sync with external page changes (e.g. clicking a numbered button).
  useEffect(() => {
    setJumpInput(String(page));
  }, [page]);

  if (totalPages <= 1) return null;

  const max = Math.min(7, totalPages);
  const start = Math.max(1, Math.min(page - 3, totalPages - max + 1));

  const submitJump = () => {
    const n = parseInt(jumpInput, 10);
    if (!Number.isFinite(n)) return;
    const clamped = Math.max(1, Math.min(totalPages, n));
    if (clamped !== page) onChange(clamped);
    setJumpInput(String(clamped));
  };

  const btn =
    "px-2.5 py-1.5 border border-gray-300 rounded text-sm hover:bg-gray-50 disabled:opacity-50 disabled:hover:bg-white";

  return (
    <div className="flex flex-wrap justify-center items-center gap-1 mt-4">
      <button className={btn} disabled={page <= 1} onClick={() => onChange(1)} aria-label="First page">
        «
      </button>
      <button className={btn} disabled={page <= 1} onClick={() => onChange(page - 1)}>
        ← Prev
      </button>

      {Array.from({ length: max }, (_, i) => start + i).map((p) => (
        <button
          key={p}
          className={`${btn} ${p === page ? "bg-tg-primary text-white border-tg-primary hover:bg-tg-primary" : ""}`}
          onClick={() => onChange(p)}
        >
          {p}
        </button>
      ))}

      <button className={btn} disabled={page >= totalPages} onClick={() => onChange(page + 1)}>
        Next →
      </button>
      <button className={btn} disabled={page >= totalPages} onClick={() => onChange(totalPages)} aria-label="Last page">
        »
      </button>

      <span className="text-xs text-gray-500 ml-3">
        of {totalPages.toLocaleString()}
      </span>

      <span className="ml-3 flex items-center gap-1">
        <input
          type="number"
          min={1}
          max={totalPages}
          value={jumpInput}
          onChange={(e) => setJumpInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submitJump();
          }}
          className="w-20 px-2 py-1.5 border border-gray-300 rounded text-sm"
          aria-label="Jump to page"
        />
        <button className={btn} onClick={submitJump}>
          Go
        </button>
      </span>
    </div>
  );
}
