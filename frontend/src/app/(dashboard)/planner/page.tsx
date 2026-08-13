"use client";

import { useState } from "react";
import { createPlan, generateMarketing, LessonPlan } from "@/lib/api";
import { Sparkles, Save, Download, BookOpen, Plus } from "lucide-react";

const tabs = ["Objectives", "Warm-up", "Explanation", "Practice Set"] as const;
type Tab = (typeof tabs)[number];

const levelOptions = [
  "Math 8: Pre-Algebra",
  "Math 9: Algebra",
  "Math 10: Geometry",
  "Math 11: Pre-Calculus",
  "Calculus 1",
];

export default function PlannerPage() {
  const [topic, setTopic] = useState("");
  const [level, setLevel] = useState("Math 11: Pre-Calculus");
  const [duration, setDuration] = useState(60);
  const [plan, setPlan] = useState<LessonPlan | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("Objectives");
  const [loading, setLoading] = useState(false);

  const handleGenerate = async () => {
    if (!topic) return;
    setLoading(true);
    try {
      const result = await createPlan({
        topic,
        grade_level: level.toLowerCase(),
        duration_min: duration,
      });
      setPlan(result);
      setActiveTab("Objectives");
    } catch {
      alert("Plan generation failed.");
    } finally {
      setLoading(false);
    }
  };

  const renderTabContent = () => {
    if (!plan) return null;
    switch (activeTab) {
      case "Objectives":
        return (
          <div>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center">
                <span className="text-blue-600 text-lg">🎯</span>
              </div>
              <div>
                <h3 className="font-bold text-lg">Learning Objectives</h3>
                <p className="text-sm text-gray-500">Defining the core competencies for this lesson.</p>
              </div>
            </div>
            <div className="space-y-3">
              {(typeof plan.objectives === "string" ? plan.objectives.split("\n").filter(Boolean) : [plan.objectives]).map((obj, i) => (
                <div key={i} className="flex items-start gap-3 bg-blue-50 rounded-xl p-4 border border-blue-100">
                  <span className="text-green-500 mt-0.5">✓</span>
                  <p className="text-sm text-gray-700">{typeof obj === "string" ? obj.replace(/^[-•]\s*/, "") : JSON.stringify(obj)}</p>
                </div>
              ))}
            </div>
          </div>
        );
      case "Warm-up":
        return (
          <div className="bg-white rounded-xl p-5">
            <h3 className="font-bold text-lg mb-3">Warm-up Activity</h3>
            <div className="text-sm text-gray-700 whitespace-pre-wrap">{typeof plan.warm_up === "string" ? plan.warm_up : JSON.stringify(plan.warm_up, null, 2)}</div>
          </div>
        );
      case "Explanation":
        return (
          <div className="bg-white rounded-xl p-5">
            <h3 className="font-bold text-lg mb-3">Main Explanation</h3>
            <div className="text-sm text-gray-700 whitespace-pre-wrap">{typeof plan.explanation === "string" ? plan.explanation : JSON.stringify(plan.explanation, null, 2)}</div>
            {plan.examples && (
              <div className="mt-6">
                <h4 className="font-semibold text-gray-700 mb-2">Worked Examples</h4>
                <div className="text-sm text-gray-700 whitespace-pre-wrap">{typeof plan.examples === "string" ? plan.examples : JSON.stringify(plan.examples, null, 2)}</div>
              </div>
            )}
          </div>
        );
      case "Practice Set":
        return (
          <div className="bg-white rounded-xl p-5">
            <h3 className="font-bold text-lg mb-3">Practice Problems</h3>
            <div className="text-sm text-gray-700 whitespace-pre-wrap">{typeof plan.practice === "string" ? plan.practice : JSON.stringify(plan.practice, null, 2)}</div>
            {plan.assessment && (
              <div className="mt-6 border-t pt-4">
                <h4 className="font-semibold text-gray-700 mb-2">Exit Ticket</h4>
                <div className="text-sm text-gray-700 whitespace-pre-wrap">{typeof plan.assessment === "string" ? plan.assessment : JSON.stringify(plan.assessment, null, 2)}</div>
              </div>
            )}
          </div>
        );
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Lesson Planner</h1>
          <p className="text-gray-500 text-sm mt-1">Design structured learning experiences with AI-enhanced problem sets.</p>
        </div>
        <div className="flex gap-3">
          <button className="flex items-center gap-2 px-4 py-2 border border-gray-200 rounded-lg text-sm font-medium hover:bg-gray-50">
            <Save size={14} /> Save Draft
          </button>
          <button className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
            <Download size={14} /> Export Plan
          </button>
        </div>
      </div>

      <div className="flex gap-6">
        {/* Left — parameters */}
        <div className="w-[400px] shrink-0 space-y-6">
          <div className="bg-white border border-gray-200 rounded-xl p-6">
            <h2 className="text-lg font-bold flex items-center gap-2 mb-6">
              <span className="text-gray-400">⚙</span> Parameters
            </h2>

            <div className="space-y-5">
              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1.5">Topic Title</label>
                <input
                  type="text"
                  placeholder="e.g., Quadratic Equations A..."
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1.5">Academic Level</label>
                <select
                  value={level}
                  onChange={(e) => setLevel(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {levelOptions.map((l) => (
                    <option key={l} value={l}>{l}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1.5">Duration (Minutes)</label>
                <div className="flex items-center gap-4">
                  <input
                    type="range"
                    min={15}
                    max={120}
                    step={5}
                    value={duration}
                    onChange={(e) => setDuration(Number(e.target.value))}
                    className="flex-1 accent-blue-600"
                  />
                  <span className="text-lg font-bold text-gray-800 w-12 text-right">{duration}m</span>
                </div>
              </div>
            </div>

            <button
              onClick={handleGenerate}
              disabled={loading || !topic}
              className="w-full mt-6 bg-blue-600 text-white py-3 rounded-xl font-semibold flex items-center justify-center gap-2 hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              <Sparkles size={18} />
              {loading ? "Generating..." : "Generate Structured Plan"}
            </button>
          </div>

          <div className="bg-white border border-gray-200 rounded-xl p-5">
            <h3 className="font-semibold text-gray-700 mb-3">Quick Integrations</h3>
            <div className="flex gap-3">
              <button className="flex-1 flex flex-col items-center gap-2 py-4 border border-gray-200 rounded-lg hover:bg-gray-50">
                <BookOpen size={20} className="text-gray-600" />
                <span className="text-xs font-medium">Pull from Bank</span>
              </button>
              <button className="flex-1 flex flex-col items-center gap-2 py-4 border border-gray-200 rounded-lg hover:bg-gray-50">
                <Plus size={20} className="text-gray-600" />
                <span className="text-xs font-medium">Fresh Problems</span>
              </button>
            </div>
          </div>
        </div>

        {/* Right — plan output */}
        <div className="flex-1">
          {plan ? (
            <>
              <div className="flex border-b border-gray-200 mb-6">
                {tabs.map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`px-5 py-3 text-sm font-medium border-b-2 transition-colors ${
                      activeTab === tab
                        ? "border-blue-600 text-blue-600"
                        : "border-transparent text-gray-500 hover:text-gray-700"
                    }`}
                  >
                    {tab}
                  </button>
                ))}
              </div>
              {renderTabContent()}
              <div className="flex justify-end gap-3 mt-8">
                <button className="px-5 py-2.5 border border-gray-200 rounded-lg text-sm font-medium hover:bg-gray-50">
                  Preview PDF
                </button>
                <button className="px-5 py-2.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
                  Assign to Class
                </button>
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center h-96 text-center">
              <CalendarDays size={48} className="text-gray-200 mb-4" />
              <h3 className="text-lg font-semibold text-gray-400">No plan generated yet</h3>
              <p className="text-sm text-gray-400 mt-1">Fill in the parameters and click Generate to create a lesson plan.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function CalendarDays({ size, className }: { size: number; className?: string }) {
  return (
    <svg width={size} height={size} className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect width="18" height="18" x="3" y="4" rx="2" ry="2" /><line x1="16" x2="16" y1="2" y2="6" /><line x1="8" x2="8" y1="2" y2="6" /><line x1="3" x2="21" y1="10" y2="10" />
    </svg>
  );
}
