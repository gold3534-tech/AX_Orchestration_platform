import type { AgentSceneModel } from '../streaming/streamingTypes';

export type Point = { x: number; y: number };

export const BACKGROUND_URL = '/assets/streaming/agent-office-background-cutout.png';
export const STAGE_BACKGROUND_URL = '/assets/streaming/stage-background.png';
export const TABLE_URL = '/assets/streaming/meeting-table-sprite-cut.png';
export const TABLE_PART_URLS = [
  '/assets/streaming/meeting-table-left-1.png',
  '/assets/streaming/meeting-table-left-2.png',
  '/assets/streaming/meeting-table-right-1.png',
  '/assets/streaming/meeting-table-right-2.png',
] as const;
export const DESK_URL = '/assets/streaming/agent-desk-cutout.png';
export const AGENT_CHAIR_LANDING_URL = '/assets/streaming/agent-chair-landing-spritesheet.png';
export const MEETING_AGENT_LANDING_URLS = [
  AGENT_CHAIR_LANDING_URL,
  '/assets/streaming/landing-char-2.png?v=meeting-landing-2',
  '/assets/streaming/landing-char-3.png?v=meeting-landing-3',
  '/assets/streaming/landing-char-4.png?v=meeting-landing-4',
] as const;
export const MEETING_AGENT_TALKING_URLS = [
  '/assets/streaming/talking-char-1.png?v=meeting-talking-1',
  '/assets/streaming/talking-char-2.png?v=meeting-talking-2',
  '/assets/streaming/talking-char-3.png?v=meeting-talking-3',
  '/assets/streaming/talking-char-4.png?v=meeting-talking-4',
] as const;
export const MEETING_AGENT_WALKING_URLS = [
  '/assets/streaming/walking-char-1.png?v=meeting-walking-1',
  '/assets/streaming/walking-char-2.png?v=meeting-walking-2',
  '/assets/streaming/walking-char-3.png?v=meeting-walking-3',
  '/assets/streaming/walking-char-4.png?v=meeting-walking-4',
] as const;
export const MEETING_AGENT_WORKING_URLS = [
  '/assets/streaming/working-char-1.png?v=meeting-working-1',
  '/assets/streaming/working-char-2.png?v=meeting-working-2',
  '/assets/streaming/working-char-3.png?v=meeting-working-3',
  '/assets/streaming/working-char-4.png?v=meeting-working-4',
] as const;
export const DESIGN_SIZE = 1254;
export const INITIAL_ZOOM = 0.98;
export const MIN_ZOOM = 0.62;
export const MAX_ZOOM = 2.4;

export const MEETING_TABLE = { x: 625, y: 530, scale: 0.3 };
export const MEETING_TABLE_SOURCE_ANCHOR = { x: 1603 * 0.5, y: 981 * 0.66 };
export const MEETING_TABLE_PARTS = [
  { id: 'left-1', sourceX: 394, sourceY: 70, width: 200, height: 228 },
  { id: 'left-2', sourceX: 580, sourceY: 0, width: 200, height: 200 },
  { id: 'right-1', sourceX: 842, sourceY: 20, width: 200, height: 200 },
  { id: 'right-2', sourceX: 1038, sourceY: 134, width: 200, height: 200 },
] as const;
export const MEETING_TABLE_Z_INDEX = 451;
export const MEETING_LANDING_Z_INDEX = 450;
export const MEETING_TABLE_PART_Z_INDEX = 449;
export const MEETING_AGENT_SLOTS = [
  { id: 'meeting-table-left-1', x: 532, y: 466, landingFlipX: false, talkingFlipX: false },
  { id: 'meeting-table-left-2', x: 606, y: 438, landingFlipX: false, talkingFlipX: false },
  { id: 'meeting-table-right-1', x: 715, y: 471, landingFlipX: true, talkingFlipX: false },
  { id: 'meeting-table-right-2', x: 790, y: 474, landingFlipX: true, talkingFlipX: false },
] as const;

export const AGENT_WALK_SCALE = 0.45;
export const STREAMING_WALK_FRAME = { width: 172, height: 384, columns: 8, rows: 2 };
export const AGENT_CHAIR_LANDING_SCALE = 0.45;
export const MEETING_AGENT_LANDING_FRAME = { width: 271, height: 500, columns: 8, rows: 1 };
export const MEETING_AGENT_TALKING_FRAME = { width: 230, height: 384, columns: 12, rows: 1 };
export const MEETING_AGENT_WALKING_FRAME = STREAMING_WALK_FRAME;
export const MEETING_AGENT_WORKING_FRAME = { width: 271, height: 500, columns: 8, rows: 1 };

export const AGENT_MOVE_SPEED = 1.35;
export const DONE_AGENT_PATH_SPEED = 8.75;

export const DESK_ALIGNMENT = { rotation: 0, skewX: 0, skewY: 0 };
export const TABLE_ALIGNMENT = { rotation: 0, skewX: 0, skewY: 0 };

export const DESKS = [
  { id: 'desk-a-1', x: 335, y: 635, scale: 0.65, zIndex: 650, ...DESK_ALIGNMENT },
  { id: 'desk-a-2', x: 465, y: 720, scale: 0.65, zIndex: 736, ...DESK_ALIGNMENT },
  { id: 'desk-a-3', x: 200, y: 740, scale: 0.65, zIndex: 742, ...DESK_ALIGNMENT },
  { id: 'desk-a-4', x: 330, y: 825, scale: 0.65, zIndex: 828, ...DESK_ALIGNMENT },
  { id: 'desk-b-1', x: 650, y: 850, scale: 0.65, zIndex: 850, ...DESK_ALIGNMENT },
  { id: 'desk-b-2', x: 780, y: 935, scale: 0.65, zIndex: 936, ...DESK_ALIGNMENT },
  { id: 'desk-b-3', x: 520, y: 960, scale: 0.65, zIndex: 942, ...DESK_ALIGNMENT },
  { id: 'desk-b-4', x: 650, y: 1045, scale: 0.65, zIndex: 1028, ...DESK_ALIGNMENT },
  { id: 'desk-c-1', x: 950, y: 640, scale: 0.65, zIndex: 640, ...DESK_ALIGNMENT },
  { id: 'desk-c-2', x: 1080, y: 725, scale: 0.65, zIndex: 726, ...DESK_ALIGNMENT },
  { id: 'desk-c-3', x: 820, y: 750, scale: 0.65, zIndex: 732, ...DESK_ALIGNMENT },
  { id: 'desk-c-4', x: 950, y: 835, scale: 0.65, zIndex: 818, ...DESK_ALIGNMENT },
] as const;

export const WORKSTATIONS = [
  { x: 295, y: 655 },
  { x: 435, y: 750 },
  { x: 170, y: 770 },
  { x: 300, y: 855 },
  { x: 620, y: 880 },
  { x: 750, y: 965 },
  { x: 490, y: 990 },
  { x: 620, y: 1075 },
  { x: 920, y: 670 },
  { x: 1050, y: 755 },
  { x: 790, y: 780 },
  { x: 920, y: 865 },
];
export const SHOW_MOCK_AGENT_COORDINATES = false;
export const MOCK_AGENT_COORDINATE_SPOTS = [
  { x: 60, y: 700 },
  { x: 190, y: 600 },
  { x: 380, y: 490 },
  { x: 646, y: 335 },
  { x: 846, y: 461 },
  { x: 865, y: 530 },
  { x: 780, y: 600 },
  { x: 655, y: 686 },
  { x: 495, y: 810 },
  { x: 350, y: 940 },
  { x: 635, y: 1150 },
  { x: 810, y: 1030 },
  { x: 960, y: 940 },
  { x: 1090, y: 826 },
  { x: 1220, y: 711 },
] as const;
export const AGENT_WALK_ROUTE = MOCK_AGENT_COORDINATE_SPOTS;
export const DONE_AGENT_PATH = [
  MOCK_AGENT_COORDINATE_SPOTS[2],
  MOCK_AGENT_COORDINATE_SPOTS[3],
  MOCK_AGENT_COORDINATE_SPOTS[4],
  MOCK_AGENT_COORDINATE_SPOTS[5],
  MOCK_AGENT_COORDINATE_SPOTS[6],
  MOCK_AGENT_COORDINATE_SPOTS[7],
  MOCK_AGENT_COORDINATE_SPOTS[2],
] as const;
export const IDLE_SPOT = { x: 625, y: 565 };
export const BLOCKED_SPOT = { x: 1030, y: 620 };

export function targetForAgent(agent: AgentSceneModel, index: number) {
  if (agent.status === 'working') return WORKSTATIONS[agent.station % WORKSTATIONS.length];
  if (agent.status === 'blocked') return { x: BLOCKED_SPOT.x, y: BLOCKED_SPOT.y + index * 22 };
  return { x: IDLE_SPOT.x + index * 44, y: IDLE_SPOT.y + (index % 2) * 28 };
}
