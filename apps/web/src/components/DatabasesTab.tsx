import { useDatabases } from "../api/queries";

export default function DatabasesTab() {
  const { data, isLoading, error } = useDatabases();
  if (isLoading) return <div className="text-gray-500">Loading…</div>;
  if (error) return <div className="text-red-600">Error: {(error as Error).message}</div>;
  if (!data) return null;

  return (
    <div className="space-y-2">
      {data.map((db) => (
        <div
          key={db.name}
          className={`border-2 rounded-md p-4 bg-white ${
            db.decrypted ? "border-green-500" : "border-red-500"
          }`}
        >
          <div className="font-mono text-sm font-semibold">{db.name}</div>
          <div className="text-xs text-gray-600 mt-1">
            {db.message_count.toLocaleString()} messages · tables: {db.tables.join(", ")}
          </div>
        </div>
      ))}
    </div>
  );
}
