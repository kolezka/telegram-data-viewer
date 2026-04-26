import { useState } from "react";
import TabNav, { type TabKey } from "./components/TabNav";

export default function App() {
  const [active, setActive] = useState<TabKey>("stats");

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-6xl mx-auto px-6 py-5">
          <h1 className="text-2xl font-bold text-gray-900">Telegram Data Viewer</h1>
        </div>
      </header>

      <div className="max-w-6xl mx-auto mt-6 bg-white rounded-lg shadow-sm overflow-hidden">
        <TabNav active={active} onChange={setActive} />
        <div className="p-6">
          {active === "stats" && <PlaceholderTab name="Stats" />}
          {active === "databases" && <PlaceholderTab name="Databases" />}
          {active === "chats" && <PlaceholderTab name="Chats" />}
          {active === "messages" && <PlaceholderTab name="Messages" />}
          {active === "users" && <PlaceholderTab name="Users" />}
          {active === "media" && <PlaceholderTab name="Media" />}
        </div>
      </div>
    </div>
  );
}

function PlaceholderTab({ name }: { name: string }) {
  return <div className="text-gray-500">{name} tab — implemented in later tasks.</div>;
}
