"use client";

import { Problem } from "@/lib/api";

interface Props {
  problem: Problem;
  status?: "verified" | "review" | "pending";
  onEdit?: () => void;
  onDelete?: () => void;
}

export default function ProblemCard({ problem, status, onEdit, onDelete }: Props) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 hover:shadow-md transition-shadow">
      <div className="flex items-center justify-between mb-4">
        <span className="text-xs text-gray-400 font-mono">
          ID: {problem.id.slice(0, 8).toUpperCase()}
        </span>
        {status === "verified" && (
          <span className="flex items-center gap-1 text-xs text-green-600 font-semibold bg-green-50 px-2 py-0.5 rounded-full">
            ✓ VERIFIED
          </span>
        )}
        {status === "review" && (
          <span className="flex items-center gap-1 text-xs text-red-600 font-semibold bg-red-50 px-2 py-0.5 rounded-full">
            ⊘ REVIEW NEEDED
          </span>
        )}
      </div>

      <div className="bg-gray-50 rounded-lg p-4 mb-4 font-mono text-sm text-center whitespace-pre-wrap">
        {problem.body}
      </div>

      {problem.solution && (
        <div className="bg-blue-50 text-blue-700 rounded-lg px-4 py-2 text-sm font-semibold text-center mb-4">
          ANSWER: {problem.solution.length > 60 ? problem.solution.slice(0, 60) + "…" : problem.solution}
        </div>
      )}

      <div className="flex flex-wrap gap-2 mb-2">
        <span className="px-2.5 py-1 bg-gray-100 text-gray-600 rounded-full text-xs">{problem.topic}</span>
        <span className="px-2.5 py-1 bg-gray-100 text-gray-600 rounded-full text-xs">{problem.grade_level}</span>
        <span className="px-2.5 py-1 bg-gray-100 text-gray-600 rounded-full text-xs capitalize">{problem.difficulty}</span>
      </div>

      {problem.source && (
        <div className="text-xs text-gray-400 mt-2">Source: {problem.source}</div>
      )}
    </div>
  );
}
