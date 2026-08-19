"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { useDropzone } from "react-dropzone";
import { extractProblems, approveProblems, saveTextbook, getIngestionRun, Problem } from "@/lib/api";
import { Upload, FileText, Copy, Trash2, Check, Library } from "lucide-react";

export default function ExtractorPage() {
  const [file, setFile] = useState<File | null>(null);
  const [startPage, setStartPage] = useState("");
  const [endPage, setEndPage] = useState("");
  const [extractSolutions, setExtractSolutions] = useState(true);
  const [autoTag, setAutoTag] = useState(true);
  const [convertLatex, setConvertLatex] = useState(false);
  const [extracted, setExtracted] = useState<Problem[]>([]);
  const [reviewIndex, setReviewIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [processing, setProcessing] = useState(false);

  // Save Textbook: independent of the extraction flow above -- own request, own
  // status, never touches `loading`/`extracted`/`extractProblems`.
  const [textbookTitle, setTextbookTitle] = useState("");
  const [edition, setEdition] = useState("");
  const [publisher, setPublisher] = useState("");
  const [savingTextbook, setSavingTextbook] = useState(false);
  const [saveStatusText, setSaveStatusText] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const onDrop = useCallback((files: File[]) => {
    if (files.length > 0) setFile(files[0]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"], "image/*": [".png", ".jpg", ".jpeg"] },
    maxSize: 50 * 1024 * 1024,
    multiple: false,
  });

  const handleExtract = async () => {
    if (!file) return;
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      if (startPage) formData.append("start_page", startPage);
      if (endPage) formData.append("end_page", endPage);
      formData.append("extract_solutions", String(extractSolutions));
      formData.append("auto_tag", String(autoTag));
      formData.append("convert_latex", String(convertLatex));
      const results = await extractProblems(formData);
      setExtracted(results);
      setReviewIndex(0);
    } catch {
      alert("Extraction failed. Check your API connection.");
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = (index: number) => {
    if (index < extracted.length - 1) setReviewIndex(index + 1);
  };

  const handleSkip = (index: number) => {
    setExtracted(extracted.filter((_, i) => i !== index));
  };

  const handleApproveAll = async () => {
    setProcessing(true);
    try {
      await approveProblems(extracted);
      setExtracted([]);
      setReviewIndex(0);
    } catch {
      alert("Failed to approve problems.");
    } finally {
      setProcessing(false);
    }
  };

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const pollSaveRun = (runId: string) => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const run = await getIngestionRun(runId);
        if (run.status === "completed") {
          const structure = run.progress?.structure as
            | { chapters_written?: number; sections_written?: number }
            | undefined;
          setSaveStatusText(
            structure
              ? `Done — ${structure.chapters_written ?? 0} chapters, ${structure.sections_written ?? 0} sections saved`
              : "Done."
          );
          setSavingTextbook(false);
          stopPolling();
        } else if (run.status === "failed") {
          setSaveStatusText(`Failed: ${run.error || "unknown error"}`);
          setSavingTextbook(false);
          stopPolling();
        } else {
          setSaveStatusText(
            run.current_stage === "structure"
              ? "Identifying chapters and sections…"
              : "Extracting pages…"
          );
        }
      } catch {
        setSaveStatusText("Lost connection while checking save status.");
        setSavingTextbook(false);
        stopPolling();
      }
    }, 2000);
  };

  const handleSaveTextbook = async () => {
    if (!file || !textbookTitle.trim()) return;
    setSavingTextbook(true);
    setSaveStatusText("Saving…");
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("title", textbookTitle.trim());
      if (startPage) formData.append("start_page", startPage);
      if (endPage) formData.append("end_page", endPage);
      if (edition.trim()) formData.append("edition", edition.trim());
      if (publisher.trim()) formData.append("publisher", publisher.trim());
      const result = await saveTextbook(formData);
      setSaveStatusText("Extracting pages…");
      pollSaveRun(result.run_id);
    } catch (error) {
      setSaveStatusText(error instanceof Error ? error.message : "Save failed.");
      setSavingTextbook(false);
    }
  };

  const current = extracted[reviewIndex];

  return (
    <div className="flex gap-6">
      {/* Left panel */}
      <div className="w-[480px] shrink-0 space-y-6">
        <div>
          <h1 className="text-2xl font-bold">Extraction Source</h1>
          <p className="text-gray-500 text-sm mt-1">Upload a textbook PDF or image to extract math problems automatically.</p>
        </div>

        <div
          {...getRootProps()}
          className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors ${
            isDragActive ? "border-blue-500 bg-blue-50" : "border-gray-300 hover:border-blue-400"
          }`}
        >
          <input {...getInputProps()} />
          {file ? (
            <div className="flex items-center gap-3 justify-center">
              <FileText size={24} className="text-blue-600" />
              <span className="font-medium">{file.name}</span>
            </div>
          ) : (
            <>
              <Upload size={32} className="mx-auto text-gray-300 mb-3" />
              <p className="font-medium text-gray-600">Click to upload or drag and drop</p>
              <p className="text-xs text-gray-400 mt-1">PDF, PNG, JPG UP TO 50MB</p>
            </>
          )}
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">Page Range (Optional)</h3>
          <div className="flex gap-4">
            <div className="flex-1">
              <label className="text-xs text-gray-500 mb-1 block">Start Page</label>
              <input
                type="number"
                placeholder="e.g. 142"
                value={startPage}
                onChange={(e) => setStartPage(e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="flex-1">
              <label className="text-xs text-gray-500 mb-1 block">End Page</label>
              <input
                type="number"
                placeholder="e.g. 145"
                value={endPage}
                onChange={(e) => setEndPage(e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-3">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Extraction Parameters</h3>
          {[
            { label: "Extract Solutions if present", checked: extractSolutions, onChange: setExtractSolutions },
            { label: "Auto-tag Difficulty & Topics", checked: autoTag, onChange: setAutoTag },
            { label: "Convert formatting to LaTeX", checked: convertLatex, onChange: setConvertLatex },
          ].map((opt) => (
            <label key={opt.label} className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={opt.checked}
                onChange={(e) => opt.onChange(e.target.checked)}
                className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <span className="text-sm text-gray-700">{opt.label}</span>
            </label>
          ))}
        </div>

        <button
          onClick={handleExtract}
          disabled={!file || loading}
          className="w-full bg-teal-700 text-white py-3.5 rounded-xl font-semibold flex items-center justify-center gap-2 hover:bg-teal-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <Sparkles size={18} />
          {loading ? "Extracting..." : "Run Extraction Agent"}
        </button>

        <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-3">
          <div>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Save Textbook</h3>
            <p className="text-xs text-gray-400 mt-1">
              Saves pages and chapter/section structure to the textbook library. Independent of extraction above.
            </p>
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Textbook Title</label>
            <input
              type="text"
              placeholder="e.g. Algebra 2"
              value={textbookTitle}
              onChange={(e) => setTextbookTitle(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500"
            />
          </div>
          <div className="flex gap-4">
            <div className="flex-1">
              <label className="text-xs text-gray-500 mb-1 block">Edition (optional)</label>
              <input
                type="text"
                value={edition}
                onChange={(e) => setEdition(e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500"
              />
            </div>
            <div className="flex-1">
              <label className="text-xs text-gray-500 mb-1 block">Publisher (optional)</label>
              <input
                type="text"
                value={publisher}
                onChange={(e) => setPublisher(e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500"
              />
            </div>
          </div>
          <button
            onClick={handleSaveTextbook}
            disabled={!file || !textbookTitle.trim() || savingTextbook}
            className="w-full bg-slate-700 text-white py-3 rounded-xl font-semibold flex items-center justify-center gap-2 hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Library size={18} />
            {savingTextbook ? "Saving..." : "Save Textbook"}
          </button>
          {saveStatusText && <p className="text-xs text-gray-500">{saveStatusText}</p>}
        </div>
      </div>

      {/* Right panel — review queue */}
      {extracted.length > 0 && (
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-6">
            <h2 className="text-xl font-bold">Pending Review</h2>
            <span className="bg-blue-100 text-blue-700 px-2.5 py-0.5 rounded-full text-xs font-semibold">
              {extracted.length} Items
            </span>
            <span className="flex items-center gap-1.5 text-xs text-blue-600">
              <span className="w-2 h-2 bg-blue-600 rounded-full animate-pulse" />
              AGENT PROCESSING...
            </span>
          </div>

          <div className="space-y-4">
            {extracted.map((problem, idx) => (
              <div key={idx} className={`bg-white border rounded-xl p-5 ${idx === reviewIndex ? "border-blue-300 shadow-sm" : "border-gray-200"}`}>
                <div className="flex items-center justify-between mb-3">
                  <span className="font-mono text-sm text-gray-500">PROB_EXT_{String(idx + 1).padStart(3, "0")}</span>
                  <div className="flex gap-1">
                    <button className="p-1.5 text-gray-400 hover:text-gray-600"><Copy size={14} /></button>
                    <button className="p-1.5 text-gray-400 hover:text-red-500"><Trash2 size={14} /></button>
                  </div>
                </div>

                {idx === reviewIndex && (
                  <>
                    <div className="mb-3">
                      <label className="text-sm text-gray-500 mb-1 block">Problem Statement</label>
                      <div className="border border-gray-200 rounded-lg p-3 font-mono text-sm bg-gray-50 whitespace-pre-wrap">
                        {problem.body}
                      </div>
                    </div>
                    {problem.solution && (
                      <div className="mb-3">
                        <label className="text-sm text-gray-500 mb-1 block">Extracted Solution (Auto-generated)</label>
                        <div className="border border-gray-200 rounded-lg p-3 font-mono text-sm bg-gray-50 whitespace-pre-wrap">
                          {problem.solution}
                        </div>
                      </div>
                    )}
                    <div className="flex items-center gap-3 mb-4">
                      <span className="text-sm text-gray-500">Tags:</span>
                      <span className="px-2.5 py-1 bg-gray-100 text-gray-600 rounded-full text-xs">{problem.topic}</span>
                      <span className="text-sm text-gray-500 ml-auto">Difficulty:</span>
                      <span className="text-sm font-medium capitalize">{problem.difficulty}</span>
                    </div>
                    <div className="flex gap-3 justify-end">
                      <button onClick={() => handleSkip(idx)} className="px-6 py-2 border border-gray-200 rounded-lg text-sm font-medium hover:bg-gray-50">
                        Skip
                      </button>
                      <button onClick={() => handleApprove(idx)} className="px-6 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium flex items-center gap-1.5 hover:bg-blue-700">
                        <Check size={14} /> Approve
                      </button>
                    </div>
                  </>
                )}

                {idx !== reviewIndex && (
                  <div className="font-mono text-sm text-gray-600 whitespace-pre-wrap line-clamp-2">
                    {problem.body}
                  </div>
                )}

                {idx !== reviewIndex && (
                  <div className="flex gap-2 mt-2">
                    <span className="px-2 py-0.5 bg-gray-100 text-gray-500 rounded text-xs">{problem.topic}</span>
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="flex items-center justify-between mt-6 pt-4 border-t border-gray-200">
            <span className="text-sm text-gray-500">
              Reviewing {reviewIndex + 1} of {extracted.length} extracted items.
            </span>
            <div className="flex gap-3">
              <button
                onClick={() => { setExtracted([]); setReviewIndex(0); }}
                className="px-5 py-2.5 border-2 border-red-200 text-red-600 rounded-lg text-sm font-semibold hover:bg-red-50"
              >
                Discard All
              </button>
              <button
                onClick={handleApproveAll}
                disabled={processing}
                className="px-5 py-2.5 bg-teal-700 text-white rounded-lg text-sm font-semibold flex items-center gap-2 hover:bg-teal-800 disabled:opacity-50"
              >
                Approve All to Bank
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Sparkles({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3l1.912 5.813a2 2 0 001.275 1.275L21 12l-5.813 1.912a2 2 0 00-1.275 1.275L12 21l-1.912-5.813a2 2 0 00-1.275-1.275L3 12l5.813-1.912a2 2 0 001.275-1.275L12 3z" />
    </svg>
  );
}
