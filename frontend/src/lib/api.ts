const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API Error ${res.status}: ${text}`);
  }
  return res.json();
}

export interface Problem {
  id: string;
  source: string;
  topic: string;
  grade_level: string;
  difficulty: string;
  body: string;
  solution: string;
  created_at?: string;
}

export interface LessonPlan {
  id: string;
  topic: string;
  grade_level: string;
  duration_min: number;
  objectives: string;
  warm_up: string;
  explanation: string;
  examples: string;
  practice: string;
  assessment: string;
  marketing_copy: string;
  created_at?: string;
}

export interface GradingSession {
  id: string;
  problem_id: string;
  student_label: string;
  work_input: string;
  diagnosis: Record<string, unknown>;
  follow_up_ids: string[];
  created_at?: string;
}

// Problem Bank
export const getProblems = (params?: Record<string, string>) => {
  const query = params ? "?" + new URLSearchParams(params).toString() : "";
  return request<Problem[]>(`/problems${query}`);
};
export const getProblem = (id: string) => request<Problem>(`/problems/${id}`);
export const createProblem = (data: Omit<Problem, "id" | "created_at">) =>
  request<Problem>("/problems", { method: "POST", body: JSON.stringify(data) });
export const deleteProblem = (id: string) =>
  request(`/problems/${id}`, { method: "DELETE" });

// Generator
export const generateProblems = (data: {
  topic: string;
  grade_level: string;
  difficulty: string;
  count: number;
  style_reference?: string;
}) => request<Problem[]>("/generate", { method: "POST", body: JSON.stringify(data) });

// Extractor
export const extractProblems = (formData: FormData) =>
  fetch(`${API_URL}/extract`, { method: "POST", body: formData }).then((r) => {
    if (!r.ok) throw new Error(`Extract failed: ${r.status}`);
    return r.json() as Promise<Problem[]>;
  });
export const approveProblems = (problems: Problem[]) =>
  request<Problem[]>("/extract/approve", { method: "POST", body: JSON.stringify(problems) });

// Planner
export const createPlan = (data: { topic: string; grade_level: string; duration_min: number }) =>
  request<LessonPlan>("/plan", { method: "POST", body: JSON.stringify(data) });
export const getPlans = () => request<LessonPlan[]>("/plan");
export const getPlan = (id: string) => request<LessonPlan>(`/plan/${id}`);
export const generateMarketing = (lesson_plan_id: string) =>
  request<LessonPlan>("/plan/marketing", { method: "POST", body: JSON.stringify({ lesson_plan_id }) });

// Grader
export const gradeSubmission = (data: { problem_id: string; student_label: string; work_input: string }) =>
  request<GradingSession>("/grade", { method: "POST", body: JSON.stringify(data) });

// Ping
export const ping = () => request<{ status: string }>("/ping");
