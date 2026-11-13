"use client";
import type { ReactNode } from "react";
import { ApiProvider } from "@/api/ApiProvider";

export function Providers({ children }: { children: ReactNode }) {
  return <ApiProvider>{children}</ApiProvider>;
}
