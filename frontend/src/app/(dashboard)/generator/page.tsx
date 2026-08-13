"use client";

import { useState } from "react";
import { generateProblems, Problem } from "@/lib/api";
import { Sparkles, Plus, Share2, HelpCircle } from "lucide-react";

const topicOptions = [
  "Quadratic Equations",
  "Linear Equations",
  "Polynomials",
  "Trigonometry",
  "Geometry",
  "Calculus",
  "Statistics",
];

export default function GeneratorPage() {
  const [topic, setTopic] = useState("Quadratic Equations");
  const [difficulty, setDifficulty] = useState("Medium");
  const [count, setCount] = useState(10);
  const [styleRef, setStyleRef] = useState("");
  const [problems, setProblems] = useState<Problem[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);

  const handleGenerate = async () => {
    setLoading(true);
    setGenerating(true);
    try {
      const results = await generateProblems({
        topic: topic.toLowerCase(),
        grade_level: "grade-9",
        difficulty: difficulty.toLowerCase(),
        count,
        style_reference: styleRef || undefined,
      });
      setProblems(results);
    } catch {
      alert("Generation failed. Check your API connection.");
    } finally {
      setLoading(false);
      setGenerating(false);
    }
  };

  const subtopicColors: Record<string, string> = {
    Factoring: "bg-green-100 text-green-700",
    "Quadratic Formula": "bg-green-100 text-green-700",
    "Completing the Square": "bg-green-100 text-green-700",
  };

  return (
    <div className="flex gap-6">
      {/* Left panel — settings */}
      <div className="w-[400px] shrink-0 space-y-6">
        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h2 className="text-lg font-bold flex items-center gap-2 mb-6">
            <span className="text-gray-400">⚙</span> Generator Settings
          </h2>

          <div className="space-y-5">
            <div>
              <label className="text-sm font-medium text-gray-700 block mb-1.5">Topic</label>
              <select
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {topicOptions.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-sm font-medium text-gray-700 block mb-1.5">Difficulty</label>
              <div className="flex gap-2">
                {["Easy", "Medium", "Hard"].map((d) => (
                  <button
                    key={d}
                    onClick={() => setDifficulty(d)}
                    className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                      difficulty === d
                        ? "bg-blue-600 text-white"
                        : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                    }`}
                  >
                    {d}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-sm font-medium text-gray-700 block mb-1.5">Problem Count</label>
              <div className="flex items-center gap-4">
                <input
                  type="range"
                  min={1}
                  max={20}
                  value={count}
                  onChange={(e) => setCount(Number(e.target.value))}
                  className="flex-1 accent-blue-600"
                />
                <span className="text-lg font-bold text-gray-800 w-8 text-right">{count}</span>
              </div>
            </div>

            <hr className="border-gray-100" />

            <div>
              <label className="text-sm font-medium text-gray-700 block mb-1.5">Style Reference (Optional)</label>
              <div className="relative">
                <input
                  type="text"
                  placeholder="Search Problem Bank..."
                  value={styleRef}
                  onChange={(e) => setStyleRef(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg pl-9 pr-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
              </div>
              <p className="text-xs text-gray-400 mt-1">Matches existing problem wording and formatting.</p>
            </div>
          </div>

          <button
            onClick={handleGenerate}
            disabled={loading}
            className="w-full mt-6 bg-blue-600 text-white py-3 rounded-xl font-semibold flex items-center justify-center gap-2 hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            <Sparkles size={18} />
            {loading ? "Generating..." : "Generate Fresh Problems"}
          </button>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h3 className="font-semibold text-gray-700 mb-2">AI Insights</h3>
          <p className="text-sm text-gray-500">
            {topic === "Quadratic Equations"
              ? 'Medium difficulty quadratics typically include factoring and the quadratic formula. Suggested inclusion: "Completing the Square" for advanced logic.'
              : `Generating ${count} ${difficulty.toLowerCase()} problems on ${topic}. The AI will vary problem structures and solution methods.`}
          </p>
        </div>
      </div>

      {/* Right panel — preview */}
      <div className="flex-1">
        {problems.length > 0 ? (
          <>
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-xl font-bold">Practice Set Preview</h2>
                <p className="text-sm text-gray-500">
                  {problems.length} Problems generated • Topic: {topic}
                </p>
              </div>
              <div className="flex gap-3">
                <button className="flex items-center gap-2 px-4 py-2 border border-gray-200 rounded-lg text-sm font-medium hover:bg-gray-50">
                  <Plus size={14} /> Add to Bank
                </button>
                <button className="flex items-center gap-2 px-4 py-2 bg-gray-800 text-white rounded-lg text-sm font-medium hover:bg-gray-900">
                  <Share2 size={14} /> Export to Google Classroom
                </button>
              </div>
            </div>

            <div className="space-y-4">
              {problems.map((problem, idx) => {
                const subtopic = "Factoring";
                const colorClass = subtopicColors[subtopic] || "bg-green-100 text-green-700";
                return (
                  <div key={idx} className="bg-white border border-gray-200 rounded-xl p-6">
                    <span className={`inline-block px-2.5 py-0.5 rounded text-xs font-semibold mb-3 ${colorClass}`}>
                      #{idx + 1} • {subtopic}
                    </span>
                    <p className="text-gray-800 mb-4 whitespace-pre-wrap">{problem.body}</p>
                    {problem.solution && (
                      <div className="border-l-3 border-green-500 pl-4">
                        <span className="text-xs font-bold text-green-600 uppercase tracking-wider">Solution</span>
                        <p className="text-sm text-gray-600 mt-1 font-mono whitespace-pre-wrap">{problem.solution}</p>
                      </div>
                    )}
                  </div>
                );
              })}

              {generating && (
                <div className="border-2 border-dashed border-gray-200 rounded-xl p-12 text-center">
                  <Sparkles size={32} className="mx-auto text-gray-300 mb-3 animate-pulse" />
                  <p className="text-sm text-gray-400">AI is generating {count - problems.length} more problems...</p>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center justify-center h-96 text-center">
            <Sparkles size={48} className="text-gray-200 mb-4" />
            <h3 className="text-lg font-semibold text-gray-400">No problems generated yet</h3>
            <p className="text-sm text-gray-400 mt-1">Configure settings and click Generate to create practice problems.</p>
          </div>
        )}

        <button className="fixed bottom-6 right-6 w-12 h-12 bg-green-500 text-white rounded-full shadow-lg flex items-center justify-center hover:bg-green-600">
          <HelpCircle size={20} />
        </button>
      </div>
    </div>
  );
}
