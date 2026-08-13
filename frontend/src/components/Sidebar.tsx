"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookOpen,
  FileText,
  Sparkles,
  CalendarDays,
  ClipboardCheck,
  Settings,
  HelpCircle,
  Plus,
} from "lucide-react";

const navItems = [
  { href: "/bank", label: "Problem Bank", icon: BookOpen },
  { href: "/extractor", label: "Extract Problems", icon: FileText },
  { href: "/generator", label: "Generate Practice", icon: Sparkles },
  { href: "/planner", label: "Lesson Planner", icon: CalendarDays },
  { href: "/grader", label: "Diagnostic Grader", icon: ClipboardCheck },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 bg-white border-r border-gray-200 flex flex-col h-screen fixed left-0 top-0 z-30">
      <div className="p-5 border-b border-gray-200">
        <Link href="/" className="flex items-center gap-2">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
            <span className="text-white font-bold text-sm">Σ</span>
          </div>
          <div>
            <div className="font-bold text-blue-600 text-sm">MathFlow AI</div>
            <div className="text-[10px] text-gray-400">Internal Tutoring Labs</div>
          </div>
        </Link>
      </div>

      <div className="p-3">
        <button className="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors">
          <Plus size={16} />
          New Session
        </button>
      </div>

      <nav className="flex-1 px-3 space-y-1">
        {navItems.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                active
                  ? "bg-blue-50 text-blue-600 border-l-3 border-blue-600"
                  : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
              }`}
            >
              <item.icon size={18} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="p-3 border-t border-gray-200 space-y-1">
        <button className="flex items-center gap-3 px-3 py-2.5 text-sm text-gray-500 hover:text-gray-700 w-full rounded-lg hover:bg-gray-50">
          <Settings size={18} />
          Settings
        </button>
        <button className="flex items-center gap-3 px-3 py-2.5 text-sm text-gray-500 hover:text-gray-700 w-full rounded-lg hover:bg-gray-50">
          <HelpCircle size={18} />
          Support
        </button>
      </div>
    </aside>
  );
}
