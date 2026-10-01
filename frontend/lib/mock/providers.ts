import { Provider } from "@/types";

export const providers: Provider[] = [
  { id: "groq", name: "Groq", description: "Fast inference, cost effective", status: "Active", models: [{ id: "llama-3.1-8b-instant", name: "llama-3.1-8b-instant" }, { id: "llama-3.1-70b-versatile", name: "llama-3.1-70b-versatile" }, { id: "mixtral-8x7b-32768", name: "mixtral-8x7b-32768" }, { id: "gemma-7b-it", name: "gemma-7b-it" }] },
  { id: "openai", name: "OpenAI", description: "Advanced reasoning and tool use", status: "Inactive", models: [{ id: "gpt-4o-mini", name: "gpt-4o-mini" }, { id: "gpt-4.1", name: "gpt-4.1" }] },
  { id: "gemini", name: "Google Gemini", description: "Google multimodal models", status: "Inactive", models: [{ id: "gemini-1.5-pro", name: "gemini-1.5-pro" }] },
  { id: "huggingface", name: "Hugging Face", description: "Open model hosting and inference", status: "Inactive", models: [{ id: "mistral-7b", name: "mistral-7b" }] }
];
