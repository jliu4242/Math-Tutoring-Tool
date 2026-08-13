"use client";

import { Search, Bell, Play, User } from "lucide-react";

export default function TopBar() {
  return (
    <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-6 fixed top-0 left-64 right-0 z-20">
      <div className="flex items-center gap-6">
        <span className="text-blue-600 font-semibold text-sm">Math Tutor Laboratory</span>
        <nav className="flex items-center gap-4 text-sm text-gray-500">
          <button className="hover:text-gray-900">Workspaces</button>
          <button className="hover:text-gray-900">Recent Jobs</button>
        </nav>
      </div>

      <div className="flex-1 max-w-md mx-8">
        <div className="relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search problems..."
            className="w-full pl-9 pr-4 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-full text-sm font-medium hover:bg-blue-700 transition-colors">
          <Play size={14} />
          Run Diagnostics
        </button>
        <button className="p-2 text-gray-400 hover:text-gray-600 relative">
          <Bell size={20} />
        </button>
        <button className="w-8 h-8 bg-gray-200 rounded-full flex items-center justify-center">
          <User size={16} className="text-gray-500" />
        </button>
      </div>
    </header>
  );
}
