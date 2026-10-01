"use client";
import { useRef, useEffect, useState } from "react";
import { Send, Bot, User, Sparkles, ShoppingCart, Search, Truck } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import WithLayout from "@/components/layout/with-layout";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { products } from "@/lib/mock/chat";
import { sendMessage } from "@/lib/api/chat";
import { ChatMessage } from "@/types";
import { cn } from "@/lib/utils";
import { IllustrationChatEmpty } from "@/components/ui/illustrations";

const QUICK_ACTIONS = [
  { label: "Find a product",   icon: Search,      prompt: "Show all products"  },
  { label: "Compare products", icon: Sparkles,    prompt: "Compare products"   },
  { label: "Track my order",   icon: Truck,       prompt: "Track my order"     },
  { label: "View my cart",     icon: ShoppingCart, prompt: "Show my cart"      },
] as const;

export default function ChatPage() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  const mutation = useMutation({
    mutationFn: sendMessage,
    onSuccess: (reply) =>
      setMessages((m) => [
        ...m,
        {
          ...reply,
          createdAt: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]),
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, mutation.isPending]);

  function submit(text = input) {
    const trimmed = text.trim();
    if (!trimmed) return;
    setMessages((m) => [
      ...m,
      {
        id: crypto.randomUUID(),
        role: "user",
        content: trimmed,
        createdAt: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      },
    ]);
    setInput("");
    mutation.mutate({ message: trimmed, application: "all" });
  }

  return (
    <WithLayout>
      {/* Full-height chat layout */}
      <div className="flex h-[calc(100vh-56px-48px)] flex-col">

        {/* Chat header */}
        <div className="flex shrink-0 items-center justify-between rounded-t-lg border border-border bg-card px-5 py-3">
          <div className="flex items-center gap-2.5">
            <div className="grid h-8 w-8 place-items-center rounded-lg bg-primary">
              <Bot className="h-4 w-4 text-white" />
            </div>
            <div>
              <p className="text-sm font-semibold text-foreground">Master Chatbot</p>
              <div className="flex items-center gap-1.5">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-75"
                    style={{ animationDuration: "2s" }} />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-success" />
                </span>
                <p className="text-xs text-muted-foreground">Online · All Applications</p>
              </div>
            </div>
          </div>
          <Select className="w-44">
            <option>All Applications</option>
            <option>E-commerce</option>
            <option>Hospital Management</option>
            <option>Pharmacy</option>
          </Select>
        </div>

        {/* Messages area */}
        <Card className="flex flex-1 flex-col overflow-hidden rounded-t-none border-t-0">
          <div className="flex-1 overflow-y-auto px-5 py-5 space-y-4">

            {messages.length === 0 ? (
              /* ── Empty state ── */
              <div className="flex h-full flex-col items-center justify-center py-10 text-center">
                <IllustrationChatEmpty className="mb-5 h-36 w-auto" />
                <h2 className="text-lg font-bold text-foreground">Start a conversation</h2>
                <p className="mt-2 max-w-xs text-sm text-muted-foreground">
                  Ask about products, orders, inventory or anything across your connected applications.
                </p>
                {/* Quick actions grid */}
                <div className="mt-6 grid grid-cols-2 gap-2 w-full max-w-xs">
                  {QUICK_ACTIONS.map(({ label, icon: Icon, prompt }) => (
                    <button key={label} onClick={() => submit(prompt)}
                      className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2.5 text-left text-sm font-medium text-foreground transition-all hover:border-primary/30 hover:bg-primary/5 hover:text-primary">
                      <Icon className="h-3.5 w-3.5 shrink-0 text-primary" />
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <>
                {messages.map((m) => (
                  <div key={m.id}
                    className={cn("msg-enter flex gap-3", m.role === "user" ? "flex-row-reverse" : "flex-row")}>
                    {/* Avatar */}
                    <div className={cn(
                      "mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs font-bold",
                      m.role === "user" ? "bg-primary text-white" : "bg-muted text-muted-foreground"
                    )}>
                      {m.role === "user"
                        ? <User className="h-3.5 w-3.5" />
                        : <Bot className="h-3.5 w-3.5" />}
                    </div>

                    {/* Bubble */}
                    <div className={cn(
                      "max-w-[75%] rounded-xl px-4 py-3 text-sm",
                      m.role === "user"
                        ? "bg-primary text-white rounded-tr-sm"
                        : "bg-muted text-foreground rounded-tl-sm"
                    )}>
                      <p className="leading-relaxed">{m.content}</p>

                      {/* Product cards */}
                      {m.role === "assistant" && m.content.includes("products") && (
                        <div className="mt-3 grid gap-2 sm:grid-cols-3">
                          {products.map((p) => (
                            <div key={p.id}
                              className="rounded-lg border border-border bg-card p-3 text-foreground shadow-sm">
                              <p className="text-xs font-semibold">{p.name}</p>
                              <p className="mt-0.5 text-sm font-bold text-primary">{p.price}</p>
                              <p className="text-xs text-muted-foreground">Stock: {p.stock}</p>
                              <Button className="mt-2 w-full" size="sm">Add to Cart</Button>
                            </div>
                          ))}
                        </div>
                      )}

                      <p className={cn(
                        "mt-1.5 text-2xs",
                        m.role === "user" ? "text-right text-white/60" : "text-muted-foreground"
                      )}>
                        {m.createdAt}
                      </p>
                    </div>
                  </div>
                ))}

                {/* Typing indicator */}
                {mutation.isPending && (
                  <div className="msg-enter flex gap-3">
                    <div className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-muted">
                      <Bot className="h-3.5 w-3.5 text-muted-foreground" />
                    </div>
                    <div className="flex items-center gap-1 rounded-xl rounded-tl-sm bg-muted px-4 py-3">
                      {[0, 150, 300].map((delay) => (
                        <span key={delay}
                          className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 animate-bounce"
                          style={{ animationDelay: `${delay}ms`, animationDuration: "1s" }} />
                      ))}
                    </div>
                  </div>
                )}
                <div ref={bottomRef} />
              </>
            )}
          </div>

          {/* Input area */}
          <div className="shrink-0 border-t border-border p-4">
            {/* Quick action chips when conversation is active */}
            {messages.length > 0 && (
              <div className="mb-3 flex flex-wrap gap-1.5">
                {QUICK_ACTIONS.map(({ label, prompt }) => (
                  <button key={label} onClick={() => submit(prompt)}
                    className="rounded-full border border-border bg-muted px-3 py-1 text-xs font-medium text-muted-foreground transition-all hover:border-primary/30 hover:bg-primary/5 hover:text-primary">
                    {label}
                  </button>
                ))}
              </div>
            )}

            <div className="flex gap-2">
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && submit()}
                placeholder="Type your message…"
                className="flex-1"
                aria-label="Chat message"
              />
              <Button
                onClick={() => submit()}
                disabled={!input.trim() || mutation.isPending}
                aria-label="Send message"
              >
                <Send className="h-4 w-4" />
              </Button>
            </div>
            <p className="mt-2 text-center text-2xs text-muted-foreground">
              Powered by Master Chatbot · AI responses may be inaccurate
            </p>
          </div>
        </Card>
      </div>
    </WithLayout>
  );
}
