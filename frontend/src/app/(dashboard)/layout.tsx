"use client";

import Sidebar from "@/components/Sidebar";
import TopBar from "@/components/TopBar";
import { useEffect } from "react";
import { ping } from "@/lib/api";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    ping().catch(() => {});
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <Sidebar />
      <TopBar />
      <main className="ml-64 pt-16 p-6">{children}</main>
    </div>
  );
}
