"use client";

import { useState } from "react";
import { gradeSubmission, GradingSession } from "@/lib/api";
import { Upload, CheckCircle, XCircle, ChevronDown } from "lucide-react";

export default function GraderPage() {
  const [problemId, setProblemId] = useState("");
  const [problemLabel, setProblemLabel] = useState("ALG-204: Quadratic Roots");
  const [studentWork, setStudentWork] = useState("");
  const [studentLabel, setStudentLabel] = useState("Student A");
  const [session, setSession] = useState<GradingSession | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploadedImage, setUploadedImage] = useState<string | null>(null);

  const handleGrade = async () => {
    if (!problemId || !studentWork) return;
    setLoading(true);
    try {
      const result = await gradeSubmission({
        problem_id: problemId,
        student_label: studentLabel,
        work_input: studentWork,
      });
      setSession(result);
    } catch {
      alert("Grading failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (ev) => setUploadedImage(ev.target?.result as string);
      reader.readAsDataURL(file);
    }
  };

  const diagnosis = session?.diagnosis as Record<string, unknown> | undefined;
  const steps = (diagnosis?.steps as Array<Record<string, unknown>>) || [];
  const score = (diagnosis?.score as string) || "";
  const errorType = (diagnosis?.error_type as string) || "";
  const confidence = (diagnosis?.confidence as number) || 0;
  const feedback = (diagnosis?.feedback as string) || "";

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Diagnostic Grader</h1>
          <p className="text-gray-500 text-sm mt-1">Upload student work to analyze conceptual gaps and procedural errors.</p>
        </div>
        <div className="flex items-center gap-2 text-sm text-green-600 bg-green-50 px-3 py-1.5 rounded-full">
          <span className="w-2 h-2 bg-green-500 rounded-full" />
          SYSTEM READY
        </div>
      </div>

      {/* Top info cards */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider block mb-2">Target Problem</label>
          <div className="flex items-center gap-2 border border-gray-200 rounded-lg px-3 py-2">
            <span className="text-gray-400">Σ</span>
            <input
              type="text"
              value={problemLabel}
              onChange={(e) => setProblemLabel(e.target.value)}
              className="flex-1 text-sm focus:outline-none"
            />
            <button className="text-gray-400"><ChevronDown size={14} /></button>
          </div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4 text-center">
          <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider block mb-2">Diagnostic Score</label>
          <div className="text-3xl font-bold">
            {score ? (
              <><span className="text-red-500">{score.split("/")[0]}</span>/<span className="text-gray-400">{score.split("/")[1]}</span> <span className="text-sm font-normal text-gray-400">pts</span></>
            ) : (
              <span className="text-gray-300">—</span>
            )}
          </div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4 text-center">
          <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider block mb-2">Error Type</label>
          <div className="text-sm font-semibold text-gray-700">{errorType ? `Procedural (${errorType})` : "—"}</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4 text-center">
          <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider block mb-2">Confidence</label>
          <div className={`text-lg font-bold ${confidence > 90 ? "text-green-600" : "text-yellow-600"}`}>
            {confidence ? `${confidence}%` : "—"}
          </div>
        </div>
      </div>

      <div className="flex gap-6">
        {/* Left — student submission */}
        <div className="w-1/2 space-y-4">
          <div className="bg-white border border-gray-200 rounded-xl p-5">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Student Submission</h3>

            {uploadedImage ? (
              <div className="relative">
                <img src={uploadedImage} alt="Student work" className="w-full rounded-lg border border-gray-200" />
                <button
                  onClick={() => setUploadedImage(null)}
                  className="absolute top-2 right-2 bg-white rounded-full p-1 shadow"
                >
                  <XCircle size={16} className="text-gray-400" />
                </button>
              </div>
            ) : (
              <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
                <Upload size={24} className="mx-auto text-gray-300 mb-2" />
                <p className="text-sm text-gray-500 mb-2">Upload an image of student work</p>
                <label className="cursor-pointer text-sm text-blue-600 hover:text-blue-700 font-medium">
                  Choose file
                  <input type="file" className="hidden" accept="image/*" onChange={handleImageUpload} />
                </label>
              </div>
            )}

            <div className="mt-4">
              <label className="text-sm font-medium text-gray-700 block mb-1.5">Or type student&apos;s work</label>
              <textarea
                value={studentWork}
                onChange={(e) => setStudentWork(e.target.value)}
                placeholder="Enter the student's solution steps..."
                rows={4}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div className="mt-4 flex gap-3">
              <input
                type="text"
                placeholder="Problem ID"
                value={problemId}
                onChange={(e) => setProblemId(e.target.value)}
                className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                onClick={handleGrade}
                disabled={loading || (!studentWork && !uploadedImage)}
                className="px-6 py-2 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700 disabled:opacity-50"
              >
                {loading ? "Grading..." : "Run Diagnosis"}
              </button>
            </div>
          </div>
        </div>

        {/* Right — agent reconstruction */}
        <div className="w-1/2">
          {session ? (
            <div className="bg-white border border-gray-200 rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Agent Reconstruction</h3>
                <button className="text-sm text-blue-600 hover:text-blue-700 font-medium">View Raw Log</button>
              </div>

              <div className="space-y-4">
                {steps.map((step, idx) => (
                  <div key={idx}>
                    <div className="flex items-center gap-2 mb-2">
                      {step.correct ? (
                        <CheckCircle size={16} className="text-green-500" />
                      ) : (
                        <XCircle size={16} className="text-red-500" />
                      )}
                      <span className={`text-sm font-semibold ${step.correct ? "text-gray-700" : "text-red-600"}`}>
                        Step {String(step.step_number)}: {String(step.description)}
                        {!step.correct && " (ERROR DETECTED)"}
                      </span>
                    </div>
                    <div className={`rounded-lg p-3 font-mono text-sm ${step.correct ? "bg-gray-50" : "bg-red-50 border border-red-200"}`}>
                      {String(step.work)}
                    </div>
                    {!step.correct && !!step.error_detail && (
                      <div className="mt-2 border-l-3 border-red-500 pl-3">
                        <p className="text-sm text-red-700">
                          <span className="font-semibold">{errorType} Error:</span> {String(step.error_detail)}
                        </p>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {feedback && (
                <div className="mt-6 pt-4 border-t border-gray-200">
                  <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Suggested Student Feedback</h4>
                  <p className="text-sm text-gray-700">{feedback}</p>
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-96 text-center">
              <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
                <Upload size={24} className="text-gray-300" />
              </div>
              <h3 className="text-lg font-semibold text-gray-400">No diagnosis yet</h3>
              <p className="text-sm text-gray-400 mt-1">Upload student work and run the diagnostic grader.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
