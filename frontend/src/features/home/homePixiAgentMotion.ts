import type { AgentSceneModel } from '../streaming/streamingTypes';
import type { HomePixiAssets } from './homePixiAssets';
import {
  AGENT_CHAIR_LANDING_SCALE,
  AGENT_MOVE_SPEED,
  AGENT_WALK_ROUTE,
  AGENT_WALK_SCALE,
  DONE_AGENT_PATH,
  DONE_AGENT_PATH_SPEED,
  MEETING_AGENT_SLOTS,
  MEETING_LANDING_Z_INDEX,
  type Point,
  targetForAgent,
} from './homePixiConfig';
import { nextRouteWaypoint, pointOnPath, walkDirectionForDelta } from './homePixiMotion';

type PixiModule = typeof import('pixi.js');
type PixiContainer = InstanceType<PixiModule['Container']>;
type PixiAnimatedSprite = InstanceType<PixiModule['AnimatedSprite']>;
type PixiTexture = InstanceType<PixiModule['Texture']>;

const MIN_TALKING_TIME_AFTER_LANDING = 90;

export type PersistedAgent = {
  x: number;
  y: number;
  bob: number;
  row: number;
};

export type RuntimeAgentMember = {
  root: PixiContainer;
  sprite: PixiAnimatedSprite;
  status: AgentSceneModel['status'];
  bob: number;
  row: number;
  scaleX: number;
  isLanding: boolean;
  motionIndex: number;
  animation: 'landing' | 'talking' | 'walking' | 'working';
  landingTime?: number;
  talkingHoldTime?: number;
  hasShownTalking?: boolean;
  routeDestinationKey?: string;
  routeVisitedIndexes: Set<number>;
};

type RuntimeAgentHandlers = {
  showTooltip: (agentId: string, event: PointerEvent) => void;
  updateTooltipPosition: (event: PointerEvent) => void;
  hideTooltip: () => void;
};

function framesForMotion<T>(frames: readonly T[], motionIndex: number): T | undefined {
  return frames[motionIndex];
}

function walkingFramesForMotion(assets: HomePixiAssets, motionIndex: number, row: number) {
  return framesForMotion(assets.meetingAgentWalkingFrames, motionIndex)?.[row] ?? [];
}

function workingFramesForMotion(assets: HomePixiAssets, motionIndex: number) {
  return framesForMotion(assets.meetingAgentWorkingFrames, motionIndex) ?? [];
}

function applyMeetingAgentScale(
  sprite: PixiAnimatedSprite,
  slot: (typeof MEETING_AGENT_SLOTS)[number],
  phase: 'landing' | 'talking',
) {
  const scale = phase === 'landing' ? AGENT_CHAIR_LANDING_SCALE : AGENT_WALK_SCALE;
  const shouldFlip = phase === 'landing' ? slot.landingFlipX : slot.talkingFlipX;
  sprite.scale.set(shouldFlip ? -scale : scale, scale);
}

function setTalkingAnimation(member: RuntimeAgentMember, assets: HomePixiAssets) {
  const slot = MEETING_AGENT_SLOTS[member.motionIndex];
  const talkingFrames = framesForMotion(assets.meetingAgentTalkingFrames, member.motionIndex) ?? [];
  const fallbackFrames = walkingFramesForMotion(assets, member.motionIndex, 0);
  const frames = talkingFrames.length > 0 ? talkingFrames : fallbackFrames;
  if (frames.length === 0) return;

  member.sprite.textures = frames as PixiTexture[];
  member.sprite.anchor.set(0.5, 0.92);
  applyMeetingAgentScale(member.sprite, slot, 'talking');
  member.sprite.animationSpeed = 0.16;
  member.sprite.loop = true;
  member.sprite.gotoAndPlay(0);
  member.animation = 'talking';
}

function setWalkingAnimation(member: RuntimeAgentMember, assets: HomePixiAssets, row: number, scaleX: number) {
  const walkFrames = walkingFramesForMotion(assets, member.motionIndex, row);
  if (walkFrames.length === 0) return;

  member.row = row;
  member.scaleX = scaleX;
  member.sprite.textures = walkFrames as PixiTexture[];
  member.sprite.anchor.set(0.5, 0.92);
  member.sprite.scale.set(scaleX, AGENT_WALK_SCALE);
  member.sprite.animationSpeed = 0.16;
  member.sprite.loop = true;
  member.sprite.play();
  member.animation = 'walking';
}

function setWorkingAnimation(member: RuntimeAgentMember, assets: HomePixiAssets) {
  const workFrames = workingFramesForMotion(assets, member.motionIndex);
  if (workFrames.length === 0) return;

  member.sprite.textures = workFrames as PixiTexture[];
  member.sprite.anchor.set(0.5, 0.9);
  member.sprite.scale.set(0.35);
  member.sprite.animationSpeed = 0.18;
  member.sprite.loop = true;
  member.sprite.gotoAndPlay(0);
  member.animation = 'working';
}

function moveMemberToward(member: RuntimeAgentMember, target: { x: number; y: number }, deltaTime: number) {
  const dx = target.x - member.root.x;
  const dy = target.y - member.root.y;
  const distance = Math.hypot(dx, dy);
  const step = Math.min(distance, AGENT_MOVE_SPEED * deltaTime);
  if (distance > 0) {
    member.root.x += (dx / distance) * step;
    member.root.y += (dy / distance) * step;
  }
  return { dx, dy, distance };
}

function routedTargetForMember(
  member: RuntimeAgentMember,
  destination: Point,
  options: { routeSnapDistance?: number; destinationDistance?: number } = {},
) {
  const destinationKey = `${Math.round(destination.x)}:${Math.round(destination.y)}`;
  if (member.routeDestinationKey !== destinationKey) {
    member.routeDestinationKey = destinationKey;
    member.routeVisitedIndexes.clear();
  }

  return nextRouteWaypoint(AGENT_WALK_ROUTE, member.root, destination, member.routeVisitedIndexes, options);
}

function clearRoute(member: RuntimeAgentMember) {
  member.routeDestinationKey = undefined;
  member.routeVisitedIndexes.clear();
}

export function createRuntimeAgentMember(
  PIXI: PixiModule,
  depthLayer: PixiContainer,
  assets: HomePixiAssets,
  agent: AgentSceneModel,
  persisted: PersistedAgent | undefined,
  handlers: RuntimeAgentHandlers,
) {
  const root = new PIXI.Container();
  const shadow = new PIXI.Graphics().ellipse(0, 0, 18, 7).fill({ color: 0x000000, alpha: 0.18 });
  const motionIndex = ((agent.motionIndex ?? 1) - 1) % MEETING_AGENT_SLOTS.length;
  const slot = MEETING_AGENT_SLOTS[motionIndex];
  const landingFrames = framesForMotion(assets.meetingAgentLandingFrames, motionIndex) ?? [];
  const isLanding = landingFrames.length > 0;
  const initialFrames = isLanding ? landingFrames : walkingFramesForMotion(assets, motionIndex, 0);
  const sprite = new PIXI.AnimatedSprite(initialFrames as PixiTexture[]);

  root.label = agent.id;
  root.eventMode = 'static';
  root.cursor = 'help';
  root.hitArea = new PIXI.Rectangle(-42, -118, 84, 118);
  root.position.set(slot.x, slot.y);
  root.zIndex = MEETING_LANDING_Z_INDEX;
  sprite.anchor.set(0.5, isLanding ? 0.9 : 0.92);
  applyMeetingAgentScale(sprite, slot, isLanding ? 'landing' : 'talking');
  sprite.animationSpeed = isLanding ? 0.28 : 0.16;
  sprite.loop = !isLanding;
  sprite.gotoAndPlay(0);

  root.addChild(shadow, sprite);
  root.on('pointerover', (event) => {
    const nativeEvent = event.nativeEvent;
    if (nativeEvent instanceof PointerEvent) handlers.showTooltip(agent.id, nativeEvent);
  });
  root.on('pointermove', (event) => {
    const nativeEvent = event.nativeEvent;
    if (nativeEvent instanceof PointerEvent) handlers.updateTooltipPosition(nativeEvent);
  });
  root.on('pointerout', handlers.hideTooltip);
  depthLayer.addChild(root);

  return {
    root,
    sprite,
    status: agent.status,
    bob: persisted?.bob ?? Math.random() * Math.PI * 2,
    row: persisted?.row ?? 0,
    scaleX: AGENT_WALK_SCALE,
    isLanding,
    motionIndex,
    animation: isLanding ? ('landing' as const) : ('walking' as const),
    landingTime: 0,
    talkingHoldTime: 0,
    hasShownTalking: !isLanding,
    routeVisitedIndexes: new Set<number>(),
  };
}

export function updateRuntimeAgentMember(
  member: RuntimeAgentMember,
  agent: AgentSceneModel,
  index: number,
  assets: HomePixiAssets,
  donePathLength: number,
  deltaTime: number,
) {
  const currentStatus = agent.status;
  member.status = currentStatus;
  const shouldHoldTalking = agent.hasEnteredMeeting && !member.hasShownTalking;
  const shouldGoToMeeting = member.isLanding || currentStatus === 'meeting' || shouldHoldTalking;

  if (agent.isFlowComplete) {
    clearRoute(member);
    member.sprite.gotoAndStop(0);
    member.root.rotation = 0;
    return;
  }

  if (shouldGoToMeeting) {
    const slot = MEETING_AGENT_SLOTS[member.motionIndex];
    const routeTarget = routedTargetForMember(member, slot, {
      destinationDistance: 72,
      routeSnapDistance: 14,
    });
    const dx = routeTarget.x - member.root.x;
    const dy = routeTarget.y - member.root.y;
    const distance = Math.hypot(slot.x - member.root.x, slot.y - member.root.y);
    const isAtMeeting = distance <= 3;

    member.bob += deltaTime * 0.16;

    if (member.isLanding) {
      clearRoute(member);
      member.root.position.set(slot.x, slot.y);
      member.root.zIndex = MEETING_LANDING_Z_INDEX;
      applyMeetingAgentScale(member.sprite, slot, 'landing');
      member.landingTime = (member.landingTime ?? 0) + deltaTime;
      const landingDuration = member.sprite.textures.length / (member.sprite.animationSpeed || 0.2) + 12;
      if (member.landingTime >= landingDuration) {
        member.isLanding = false;
        member.talkingHoldTime = 0;
        setTalkingAnimation(member, assets);
      }
    } else if (!isAtMeeting) {
      const direction = walkDirectionForDelta(dx, dy, AGENT_WALK_SCALE);
      const nextRow = direction.row;
      const nextScaleX = direction.scaleX;
      if (member.animation !== 'walking' || member.row !== nextRow) {
        setWalkingAnimation(member, assets, nextRow, nextScaleX);
      }
      member.sprite.scale.x = nextScaleX;
      moveMemberToward(member, routeTarget, deltaTime);
      member.root.zIndex = member.root.y;
    } else if (member.animation !== 'talking') {
      clearRoute(member);
      member.root.position.set(slot.x, slot.y);
      member.root.zIndex = MEETING_LANDING_Z_INDEX;
      member.talkingHoldTime = 0;
      setTalkingAnimation(member, assets);
    } else {
      member.talkingHoldTime = (member.talkingHoldTime ?? 0) + deltaTime;
      if ((member.talkingHoldTime ?? 0) >= MIN_TALKING_TIME_AFTER_LANDING) member.hasShownTalking = true;
    }

    return;
  }

  const destination =
    currentStatus === 'done'
      ? pointOnPath(DONE_AGENT_PATH, (member.bob * DONE_AGENT_PATH_SPEED + index * 90) % donePathLength)
      : targetForAgent(agent, index);
  const target =
    currentStatus === 'done'
      ? destination
      : routedTargetForMember(member, destination, {
          destinationDistance: 90,
          routeSnapDistance: 14,
        });
  const dx = target.x - member.root.x;
  const dy = target.y - member.root.y;
  const distance = Math.hypot(destination.x - member.root.x, destination.y - member.root.y);
  const waypointDistance = Math.hypot(dx, dy);
  const isMoving = distance > 3;
  const direction = walkDirectionForDelta(dx, dy, AGENT_WALK_SCALE);
  const nextRow = waypointDistance > 3 ? direction.row : member.row;
  const nextScaleX = waypointDistance > 3 ? direction.scaleX : member.scaleX;

  if (isMoving && (member.animation !== 'walking' || member.row !== nextRow)) {
    setWalkingAnimation(member, assets, nextRow, nextScaleX);
  }
  if (isMoving) member.sprite.scale.x = nextScaleX;

  if (waypointDistance > 0) moveMemberToward(member, target, deltaTime);
  member.root.zIndex = member.root.y;
  member.bob += deltaTime * 0.16;

  if (!isMoving && currentStatus === 'working') {
    clearRoute(member);
    if (member.animation !== 'working') setWorkingAnimation(member, assets);
    else if (!member.sprite.playing) member.sprite.play();
  } else if (isMoving || currentStatus === 'done') {
    if (!member.sprite.playing) member.sprite.play();
  } else {
    member.sprite.gotoAndStop(0);
  }

  member.root.rotation = 0;
}
