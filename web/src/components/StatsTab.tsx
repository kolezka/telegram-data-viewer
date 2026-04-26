import { useStats } from "../api/queries";

export default function StatsTab() {
  const { data, isLoading, error } = useStats();
  if (isLoading) return <div className="text-gray-500">Loading…</div>;
  if (error) return <div className="text-red-600">Error: {(error as Error).message}</div>;
  if (!data) return null;

  const cards = [
    { label: "Databases", value: data.total_databases },
    { label: "Decrypted", value: data.decrypted_databases },
    { label: "Messages", value: data.total_messages },
    { label: "Chats", value: data.total_chats },
  ];

  return (
    <div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {cards.map((c) => (
          <div key={c.label} className="bg-white border border-gray-200 rounded-lg p-5 text-center">
            <div className="text-3xl font-bold text-tg-primary">{c.value.toLocaleString()}</div>
            <div className="text-sm text-gray-600 mt-1">{c.label}</div>
          </div>
        ))}
      </div>

      <h2 className="text-lg font-semibold text-gray-900 mb-3">Per-database</h2>
      <div className="space-y-2">
        {Object.entries(data.databases).map(([name, db]) => (
          <div key={name} className="border border-gray-200 rounded-md p-4 flex items-center justify-between">
            <div>
              <div className="font-mono text-sm">{name}</div>
              <div className="text-xs text-gray-500 mt-0.5">
                {db.decrypted ? "decrypted" : "encrypted"} · {db.tables} tables
              </div>
            </div>
            <div className="text-right">
              <div className="text-xl font-semibold">{db.message_count.toLocaleString()}</div>
              <div className="text-xs text-gray-500">messages</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
