"use client";

import { useState, useEffect } from "react";
import ProblemCard from "@/components/ProblemCard";
import { getProblems, Problem } from "@/lib/api";
import { Plus } from "lucide-react";

const levels = ["Math 8", "Math 9", "Math 10", "Math 11", "Pre-Calc"];
const classes = ["Class 1", "Class 2", "Class 3", "Seminar A"];
const topics = ["Algebra", "Geometry", "Trigonometry"];
const difficulties = ["Easy", "Medium", "Hard"];

export default function ProblemBankPage() {
  const [problems, setProblems] = useState<Problem[]>([]);
  const [filters, setFilters] = useState({
    grade_level: "Math 9",
    topic: "Algebra",
    difficulty: "Medium",
    class: "Class 2",
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getProblems({
      topic: filters.topic.toLowerCase(),
      grade_level: filters.grade_level.toLowerCase().replace(" ", "-"),
      difficulty: filters.difficulty.toLowerCase(),
    })
      .then(setProblems)
      .catch(() => setProblems([]))
      .finally(() => setLoading(false));
  }, [filters]);

  const ChipGroup = ({
    label,
    options,
    value,
    onChange,
  }: {
    label: string;
    options: string[];
    value: string;
    onChange: (v: string) => void;
  }) => (
    <div className="flex items-center gap-3 mb-3">
      <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider w-32">{label}</span>
      <div className="flex gap-2">
        {options.map((opt) => (
          <button
            key={opt}
            onClick={() => onChange(opt)}
            className={`px-3.5 py-1.5 rounded-full text-sm font-medium transition-colors ${
              value === opt
                ? "bg-blue-600 text-white"
                : "bg-white border border-gray-200 text-gray-600 hover:border-blue-300"
            }`}
          >
            {opt}
          </button>
        ))}
      </div>
    </div>
  );

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Problem Bank</h1>

      <div className="mb-8">
        <ChipGroup label="Academic Level" options={levels} value={filters.grade_level} onChange={(v) => setFilters({ ...filters, grade_level: v })} />
        <ChipGroup label="Class" options={classes} value={filters.class} onChange={(v) => setFilters({ ...filters, class: v })} />
        <ChipGroup label="Topic" options={topics} value={filters.topic} onChange={(v) => setFilters({ ...filters, topic: v })} />
        <ChipGroup label="Difficulty" options={difficulties} value={filters.difficulty} onChange={(v) => setFilters({ ...filters, difficulty: v })} />
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-400">Loading problems...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {problems.map((p, i) => (
            <ProblemCard
              key={p.id}
              problem={p}
              status={i === 0 ? "verified" : i === 2 ? "review" : undefined}
            />
          ))}

          <button className="border-2 border-dashed border-gray-300 rounded-xl flex flex-col items-center justify-center py-16 hover:border-blue-400 hover:bg-blue-50/50 transition-colors group">
            <Plus size={32} className="text-gray-300 group-hover:text-blue-400 mb-3" />
            <span className="font-semibold text-gray-500 group-hover:text-blue-600">Add New Problem</span>
            <span className="text-xs text-gray-400 mt-1">Trigger Extractor or Generator</span>
          </button>
        </div>
      )}
    </div>
  );
}
