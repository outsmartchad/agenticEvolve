"use client";

import { useState, useRef, useEffect, useCallback, FormEvent } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Send, Loader2 } from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(
    async (e?: FormEvent) => {
      e?.preventDefault();
      const text = input.trim();
      if (!text || loading) return;

      const userMsg: ChatMessage = { role: "user", content: text };
      setMessages((prev) => [...prev, userMsg]);
      setInput("");
      setLoading(true);

      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text }),
        });

        if (res.status === 404) {
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: "Chat API not available" },
          ]);
          return;
        }

        if (!res.ok) {
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content: `Error: API returned ${res.status}`,
            },
          ]);
          return;
        }

        const data = await res.json();
        const reply =
          data.response ?? data.message ?? data.content ?? JSON.stringify(data);
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: String(reply) },
        ]);
      } catch {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: "Chat API not available",
          },
        ]);
      } finally {
        setLoading(false);
        inputRef.current?.focus();
      }
    },
    [input, loading]
  );

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col">
      <h1 className="mb-3 text-lg font-semibold">Chat</h1>

      {/* Message area */}
      <Card className="flex flex-1 flex-col overflow-hidden">
        <CardContent className="flex-1 overflow-y-auto p-4">
          {messages.length === 0 && (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              Send a message to start chatting
            </div>
          )}

          <div className="space-y-3">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[75%] rounded-lg px-3 py-2 text-sm ${
                    msg.role === "user"
                      ? "bg-blue-600 text-white"
                      : "bg-zinc-700 text-zinc-100"
                  }`}
                >
                  <pre className="whitespace-pre-wrap break-words font-[inherit]">
                    {msg.content}
                  </pre>
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex justify-start">
                <div className="flex items-center gap-2 rounded-lg bg-zinc-700 px-3 py-2 text-sm text-zinc-300">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Thinking...
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        </CardContent>

        {/* Input area */}
        <div className="border-t p-3">
          <form onSubmit={sendMessage} className="flex gap-2">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type a message..."
              disabled={loading}
              className="flex-1 rounded-md border bg-background px-3 py-2 text-sm outline-none ring-offset-background placeholder:text-muted-foreground focus:ring-2 focus:ring-ring disabled:opacity-50"
            />
            <Button type="submit" size="sm" disabled={loading || !input.trim()}>
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </form>
        </div>
      </Card>
    </div>
  );
}
