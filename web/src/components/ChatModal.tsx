import { useMessages } from "../api/queries";
import type { Schemas } from "../api/client";
import { formatTimestamp } from "../lib/format";

interface Props {
  chat: Schemas["Chat"];
  onClose: () => void;
}

export default function ChatModal({ chat, onClose }: Props) {
  const peerIds = chat.all_peer_ids.join(",");
  const { data, isLoading, error } = useMessages({
    peer_id: peerIds,
    per_page: 200,
  });

  return (
    <div
      className="fixed inset-0 bg-black/55 z-50 flex items-center justify-center p-5"
      onClick={onClose}
      role="dialog"
    >
      <div
        className="bg-white rounded-xl w-full max-w-3xl max-h-[90vh] flex flex-col shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center px-5 py-4 border-b border-gray-200 bg-gray-50">
          <h3 className="text-tg-primary font-semibold">
            {chat.name} <span className="text-xs text-gray-500 ml-2">{chat.message_count} msgs</span>
          </h3>
          <button
            onClick={onClose}
            className="px-3 py-1 border border-gray-300 rounded hover:bg-gray-100"
          >
            Close
          </button>
        </div>
        <div className="flex flex-col p-5 overflow-y-auto bg-[#efeae2] flex-1">
          {isLoading && <div className="text-gray-500">Loading…</div>}
          {error && <div className="text-red-600">Error: {(error as Error).message}</div>}
          {data?.messages
            .slice()
            .reverse() // backend returns newest first; flip to chronological
            .map((m, i) => (
              <div
                key={i}
                className={`conv-bubble ${
                  m.outgoing === true
                    ? "conv-bubble-outgoing"
                    : m.outgoing === false
                    ? "conv-bubble-incoming"
                    : "conv-bubble-unknown"
                }`}
              >
                <div className="whitespace-pre-wrap">{m.text || <em className="text-gray-500">(no text)</em>}</div>
                <div className="text-xs text-gray-500 mt-1">{formatTimestamp(m.timestamp)}</div>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}
