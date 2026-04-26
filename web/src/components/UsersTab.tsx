import { useState } from "react";
import { useUsers } from "../api/queries";
import Pagination from "./Pagination";

interface Props {
  onUserClick?: (name: string) => void;
}

export default function UsersTab({ onUserClick }: Props) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const { data, isLoading, error } = useUsers({ search, page, per_page: 50 });

  return (
    <div>
      <input
        type="search"
        placeholder="Search name, username, or phone…"
        className="w-full mb-4 px-3 py-2 border border-gray-300 rounded"
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setPage(1);
        }}
      />
      {isLoading && <div className="text-gray-500">Loading…</div>}
      {error && <div className="text-red-600">Error: {(error as Error).message}</div>}
      {data && (
        <>
          <div className="text-sm text-gray-500 mb-3">
            {data.total.toLocaleString()} users
          </div>
          <div className="space-y-2">
            {data.users.map((u) => (
              <button
                key={`${u.database}:${u.id}`}
                onClick={() => onUserClick?.(u.name)}
                className="w-full text-left border border-gray-200 rounded p-3 flex justify-between items-center bg-white hover:border-tg-primary hover:bg-blue-50 transition-colors"
              >
                <div>
                  <div className="font-semibold">{u.name}</div>
                  <div className="text-xs text-gray-500">
                    {u.username && `@${u.username}`}
                    {u.username && u.phone && " · "}
                    {u.phone}
                  </div>
                </div>
                <div className="text-xs text-gray-400 font-mono">{u.database}</div>
              </button>
            ))}
          </div>
          <Pagination page={data.page} totalPages={data.total_pages} onChange={setPage} />
        </>
      )}
    </div>
  );
}
