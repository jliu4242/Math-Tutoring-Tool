"use client";

import Link from "next/link";
import { BookOpen, FileText, CalendarDays, ClipboardCheck, Bell, User, Play } from "lucide-react";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-white">
      {/* Nav */}
      <header className="flex items-center justify-between px-8 py-4 border-b border-gray-100">
        <div className="flex items-center gap-8">
          <span className="font-bold text-blue-600">MathFlow AI</span>
          <nav className="flex items-center gap-5 text-sm text-gray-600">
            <Link href="/" className="text-blue-600 border-b-2 border-blue-600 pb-0.5 font-medium">Home</Link>
            <button className="hover:text-gray-900">Workspaces</button>
            <button className="hover:text-gray-900">Recent Jobs</button>
          </nav>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/bank" className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-full text-sm font-medium hover:bg-blue-700">
            <Play size={14} /> Run Diagnostics
          </Link>
          <button className="p-2 text-gray-400"><Bell size={18} /></button>
          <div className="w-8 h-8 bg-gray-200 rounded-full flex items-center justify-center"><User size={14} className="text-gray-500" /></div>
        </div>
      </header>

      {/* Hero */}
      <section className="px-8 pt-20 pb-16 max-w-7xl mx-auto">
        <div className="flex items-center gap-16">
          <div className="flex-1">
            <div className="inline-block bg-blue-50 text-blue-600 text-xs font-semibold px-3 py-1 rounded-full mb-4">
              Introducing MathFlow 2.0
            </div>
            <h1 className="text-4xl lg:text-5xl font-bold leading-tight mb-4">
              Subject-Matter Reasoning for the{" "}
              <span className="text-blue-600">Modern Educator.</span>
            </h1>
            <p className="text-gray-500 text-lg mb-8 max-w-lg">
              The AI-powered tutoring companion that handles content generation, lesson design, and diagnostic grading so you can focus on teaching.
            </p>
            <div className="flex items-center gap-4 mb-6">
              <Link href="/login" className="bg-blue-600 text-white px-6 py-3 rounded-lg font-semibold hover:bg-blue-700 transition-colors">
                Get Started Free
              </Link>
              <button className="px-6 py-3 border border-gray-200 rounded-lg font-semibold text-gray-700 hover:bg-gray-50 transition-colors">
                Book a Demo
              </button>
            </div>
            <div className="flex items-center gap-2 text-sm text-gray-400">
              <div className="flex -space-x-2">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="w-7 h-7 bg-gray-200 rounded-full border-2 border-white" />
                ))}
              </div>
              Joined by 2,000+ Math Educators
            </div>
          </div>

          <div className="hidden lg:block flex-1 relative">
            <div className="bg-gradient-to-br from-gray-800 to-gray-900 rounded-2xl p-6 shadow-2xl">
              <div className="absolute -top-4 left-1/4 bg-white rounded-xl shadow-lg px-4 py-2 flex items-center gap-2 text-sm">
                <span className="text-blue-500">✨</span> Generator Agent
              </div>
              <div className="bg-gray-700 rounded-xl h-40 mb-4 flex items-center justify-center text-gray-500">
                <span className="text-4xl opacity-30">📊</span>
              </div>
              <div className="absolute -bottom-4 right-8 bg-white rounded-xl shadow-lg px-4 py-2 flex items-center gap-2 text-sm">
                <span className="text-green-500">✓</span> Diagnostic Grader
                <div className="w-8 h-3 bg-green-400 rounded-full" />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="px-8 py-20 bg-gray-50">
        <div className="max-w-7xl mx-auto text-center mb-16">
          <h2 className="text-3xl font-bold mb-3">Automate the Academic Workflow</h2>
          <p className="text-gray-500">Purpose-built AI agents designed for the specific nuances of STEM pedagogy.</p>
        </div>

        <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-white border border-gray-200 rounded-2xl p-8 flex gap-6">
            <div className="flex-1">
              <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center mb-4">
                <FileText size={20} className="text-gray-600" />
              </div>
              <h3 className="text-lg font-bold mb-2">Extractor Agent</h3>
              <p className="text-sm text-gray-500 mb-4">
                Instantly convert handwritten notes, blurry PDFs, and textbook photos into structured, editable LaTeX or Markdown data.
              </p>
              <ul className="space-y-2 text-sm text-gray-600">
                <li className="flex items-center gap-2"><span className="text-blue-500">◉</span> Handwritten Equation Recognition</li>
                <li className="flex items-center gap-2"><span className="text-blue-500">◉</span> Diagram-to-SVG Conversion</li>
              </ul>
            </div>
            <div className="w-48 bg-gray-100 rounded-xl flex items-center justify-center">
              <span className="text-5xl opacity-20">📄</span>
            </div>
          </div>

          <div className="bg-white border border-gray-200 rounded-2xl p-8">
            <div className="w-10 h-10 bg-red-50 rounded-xl flex items-center justify-center mb-4">
              <BookOpen size={20} className="text-red-500" />
            </div>
            <h3 className="text-lg font-bold mb-2">Problem Bank</h3>
            <p className="text-sm text-gray-500 mb-4">
              Generate infinite variations of practice problems mapped to specific curriculum standards.
            </p>
            <div className="h-20 bg-gray-50 rounded-lg" />
          </div>

          <div className="bg-white border border-gray-200 rounded-2xl p-8">
            <div className="w-10 h-10 bg-blue-50 rounded-xl flex items-center justify-center mb-4">
              <CalendarDays size={20} className="text-blue-500" />
            </div>
            <h3 className="text-lg font-bold mb-2">Lesson Planner</h3>
            <p className="text-sm text-gray-500">
              Co-create 50-minute lesson plans including warm-ups, direct instruction, and exit tickets in seconds.
            </p>
          </div>

          <div className="bg-gradient-to-br from-blue-600 to-blue-700 text-white rounded-2xl p-8 relative overflow-hidden">
            <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center mb-4">
              <ClipboardCheck size={20} />
            </div>
            <h3 className="text-lg font-bold mb-2">Diagnostic Grader</h3>
            <p className="text-sm text-blue-100">
              Beyond right or wrong. Our AI identifies misconceptions and suggests specific remedial paths for every student.
            </p>
            <div className="absolute bottom-4 right-4 opacity-20">
              <svg width="80" height="80" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1"><path d="M9 11l3 3L22 4M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>
            </div>
          </div>
        </div>
      </section>

      {/* Social proof */}
      <section className="px-8 py-12 bg-gray-800 text-white">
        <div className="max-w-7xl mx-auto text-center">
          <h3 className="text-xl font-bold mb-8">Trusted by Lab Leads Globally</h3>
          <div className="flex items-center justify-center gap-16 text-gray-400">
            {["MIT Labs", "EduFlow", "Stanbury Acad.", "STEM-X"].map((name) => (
              <span key={name} className="flex items-center gap-2 text-sm">
                <span className="opacity-50">🏛</span> {name}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="px-8 py-16">
        <div className="max-w-4xl mx-auto bg-blue-600 rounded-3xl p-12 text-center text-white relative overflow-hidden">
          <h2 className="text-3xl font-bold mb-4">Ready to reclaim your weekends?</h2>
          <p className="text-blue-100 mb-8 max-w-lg mx-auto">
            Join the thousands of math teachers using MathFlow AI to automate the tedious and focus on the transformational.
          </p>
          <div className="flex items-center justify-center gap-4">
            <Link href="/login" className="bg-white text-blue-600 px-6 py-3 rounded-lg font-semibold hover:bg-blue-50 transition-colors">
              Start Your Free Trial
            </Link>
            <button className="bg-blue-500 text-white px-6 py-3 rounded-lg font-semibold hover:bg-blue-400 transition-colors">
              View Pricing Plans
            </button>
          </div>
          <p className="text-xs text-blue-200 mt-4">No credit card required. Cancel anytime.</p>
          <div className="absolute top-4 right-8 opacity-10 text-8xl font-serif">Σ</div>
        </div>
      </section>

      {/* Footer */}
      <footer className="px-8 py-12 border-t border-gray-200">
        <div className="max-w-7xl mx-auto flex justify-between">
          <div>
            <div className="font-bold text-gray-800 mb-2">MathFlow AI</div>
            <p className="text-sm text-gray-500 max-w-xs mb-4">
              Advanced reasoning agents for the modern STEM classroom. Built by educators, for educators.
            </p>
          </div>
          <div className="flex gap-16">
            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Agents</h4>
              <ul className="space-y-2 text-sm text-gray-600">
                <li>Extractor</li><li>Generator</li><li>Planner</li><li>Grader</li>
              </ul>
            </div>
            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Company</h4>
              <ul className="space-y-2 text-sm text-gray-600">
                <li>About Us</li><li>Lab Journal</li><li>Careers</li><li>Privacy</li>
              </ul>
            </div>
          </div>
        </div>
        <div className="max-w-7xl mx-auto mt-8 pt-6 border-t border-gray-100 flex items-center justify-between text-xs text-gray-400">
          <span>© 2024 MathFlow Laboratory Inc. All rights reserved.</span>
          <div className="flex gap-4">
            <span>Settings</span><span>Support</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
