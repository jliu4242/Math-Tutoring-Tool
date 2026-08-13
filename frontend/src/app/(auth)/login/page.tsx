"use client";

import { useState } from "react";
import Link from "next/link";
import { Eye, EyeOff } from "lucide-react";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    window.location.href = "/bank";
  };

  return (
    <div className="min-h-screen flex">
      {/* Left — branding */}
      <div className="hidden lg:flex w-1/2 bg-gradient-to-br from-blue-600 to-blue-800 text-white flex-col justify-center items-center p-16 relative">
        <div className="text-center">
          <div className="text-8xl font-light mb-8 opacity-90" style={{ fontStyle: "italic" }}>
            <span className="font-serif">f</span><span className="font-sans text-7xl">x</span>
          </div>
          <h1 className="text-3xl font-bold mb-4">Master the flow of numbers.</h1>
          <p className="text-blue-200 text-lg max-w-md">
            Advanced AI-powered diagnostics and lesson planning for the next generation of mathematicians.
          </p>
        </div>

        <div className="absolute bottom-8 left-8 bg-white/10 backdrop-blur-sm rounded-xl px-4 py-3 flex items-center gap-3">
          <div className="w-8 h-8 bg-green-400/20 rounded-full flex items-center justify-center">
            <span className="text-green-300 text-sm">📈</span>
          </div>
          <div>
            <div className="text-xs text-blue-200">Class Average</div>
            <div className="font-bold text-lg">+14% Improvement</div>
          </div>
        </div>
      </div>

      {/* Right — login form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-white">
        <div className="w-full max-w-md">
          <div className="flex items-center gap-2 mb-8">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-sm">Σ</span>
            </div>
            <span className="font-bold text-blue-600">MathFlow AI</span>
          </div>

          <h2 className="text-2xl font-bold mb-1">Join MathFlow AI</h2>
          <p className="text-gray-500 text-sm mb-8">Choose your entry path to start tutoring.</p>

          <button className="w-full flex items-center justify-center gap-3 py-3 border border-gray-200 rounded-xl text-sm font-medium hover:bg-gray-50 transition-colors mb-6">
            <svg width="18" height="18" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
            Continue with Google
          </button>

          <div className="relative mb-6">
            <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-gray-200" /></div>
            <div className="relative flex justify-center text-xs uppercase"><span className="bg-white px-3 text-gray-400">or email</span></div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium text-gray-700 block mb-1.5">Work Email</label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">✉</span>
                <input
                  type="email"
                  placeholder="tutor@school.edu"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full pl-10 pr-4 py-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            <div>
              <label className="text-sm font-medium text-gray-700 block mb-1.5">Password</label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">🔒</span>
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pl-10 pr-12 py-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="w-4 h-4 rounded border-gray-300 text-blue-600" />
                <span className="text-sm text-gray-600">Remember me</span>
              </label>
              <button type="button" className="text-sm text-blue-600 hover:text-blue-700 font-medium">Forgot password?</button>
            </div>

            <button type="submit" className="w-full bg-blue-600 text-white py-3 rounded-xl font-semibold hover:bg-blue-700 transition-colors">
              Get Started
            </button>
          </form>

          <p className="text-center text-sm text-gray-500 mt-6">
            Don&apos;t have an account?{" "}
            <Link href="/login" className="text-blue-600 hover:text-blue-700 font-semibold underline">Sign up for free</Link>
          </p>

          <div className="mt-8 pt-6 border-t border-gray-200 flex justify-center gap-8">
            <button className="flex flex-col items-center gap-2 text-gray-400 hover:text-gray-600">
              <div className="w-10 h-10 bg-gray-100 rounded-full flex items-center justify-center"><span className="text-lg">🎓</span></div>
              <span className="text-xs">I&apos;m a Teacher</span>
            </button>
            <button className="flex flex-col items-center gap-2 text-gray-400 hover:text-gray-600">
              <div className="w-10 h-10 bg-gray-100 rounded-full flex items-center justify-center"><span className="text-lg">👤</span></div>
              <span className="text-xs">I&apos;m a Student</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
