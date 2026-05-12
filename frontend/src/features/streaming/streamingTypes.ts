export type StreamEvent = Record<string, unknown>;

export type AgentVisualParts = {
  hair: number;
  top: number;
  bottom: number;
  face: number;
};

export type AgentSceneStatus = 'idle' | 'working' | 'meeting' | 'done' | 'blocked';

export type AgentSceneModel = {
  id: string;
  name: string;
  status: AgentSceneStatus;
  station: number;
  parts: AgentVisualParts;
  lastMessage: string;
  // optional runtime metadata populated from snapshot or API
  meta?: {
    role?: string | null;
    details?: string | null;
    versionId?: string | null;
    goal?: string | null;
  };
  // motion index 1..4 depending on creation order; used to pick landing/talking variants
  motionIndex?: number;
  // creation order (0-based)
  createdOrder?: number;
  hasEnteredMeeting?: boolean;
  isFlowComplete?: boolean;
};

export type SceneLogLine = {
  id: string;
  level: 'system' | 'agent' | 'hitl' | 'error';
  timestamp: string;
  source: string;
  message: string;
};
