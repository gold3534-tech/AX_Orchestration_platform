export type FlowTone = 'cyan' | 'violet' | 'amber' | 'emerald';

export type FlowNode = {
  id: string;
  title: string;
  subtitle: string;
  tone: FlowTone;
  x: number;
  y: number;
};

export type FlowEdge = {
  id: string;
  source: string;
  target: string;
  label: string;
};

export const flowToneClasses: Record<FlowTone, string> = {
  cyan: 'border-cyan-300/50 bg-cyan-300/10 text-cyan-100 shadow-[0_0_0_1px_rgba(125,211,252,0.12)]',
  violet: 'border-violet-300/50 bg-violet-300/10 text-violet-100 shadow-[0_0_0_1px_rgba(196,181,253,0.12)]',
  amber: 'border-amber-300/50 bg-amber-300/10 text-amber-100 shadow-[0_0_0_1px_rgba(252,211,77,0.12)]',
  emerald: 'border-emerald-300/50 bg-emerald-300/10 text-emerald-100 shadow-[0_0_0_1px_rgba(110,231,183,0.12)]',
};

export const crewCanvasNodes: FlowNode[] = [
  {
    id: 'brief',
    title: 'Crew brief',
    subtitle: 'Intent, guardrails, and success criteria',
    tone: 'cyan',
    x: 34,
    y: 48,
  },
  {
    id: 'planner',
    title: 'Planner agent',
    subtitle: 'Breaks work into executable steps',
    tone: 'violet',
    x: 292,
    y: 28,
  },
  {
    id: 'executor',
    title: 'Executor agent',
    subtitle: 'Owns the main work stream',
    tone: 'amber',
    x: 286,
    y: 178,
  },
  {
    id: 'reviewer',
    title: 'Reviewer agent',
    subtitle: 'Checks the final result',
    tone: 'emerald',
    x: 548,
    y: 104,
  },
];

export const crewCanvasEdges: FlowEdge[] = [
  { id: 'brief-planner', source: 'brief', target: 'planner', label: 'plan' },
  { id: 'brief-executor', source: 'brief', target: 'executor', label: 'activate' },
  { id: 'planner-reviewer', source: 'planner', target: 'reviewer', label: 'handoff' },
  { id: 'executor-reviewer', source: 'executor', target: 'reviewer', label: 'verify' },
];

export const miniFlowSurfaceClassName =
  'react-flow relative overflow-hidden rounded-[28px] border border-stone-200 bg-white';
