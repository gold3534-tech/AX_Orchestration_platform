import { useEffect, useRef, useState } from 'react';
import type { AgentSceneModel } from '../streaming/streamingTypes';
import { loadHomePixiAssets } from './homePixiAssets';
import {
  DESIGN_SIZE,
  DESKS,
  DONE_AGENT_PATH,
  INITIAL_ZOOM,
  MAX_ZOOM,
  MEETING_TABLE,
  MEETING_TABLE_PARTS,
  MEETING_TABLE_PART_Z_INDEX,
  MEETING_TABLE_SOURCE_ANCHOR,
  MEETING_TABLE_Z_INDEX,
  MIN_ZOOM,
  MOCK_AGENT_COORDINATE_SPOTS,
  SHOW_MOCK_AGENT_COORDINATES,
  TABLE_ALIGNMENT,
} from './homePixiConfig';
import {
  createRuntimeAgentMember,
  type PersistedAgent,
  type RuntimeAgentMember,
  updateRuntimeAgentMember,
} from './homePixiAgentMotion';
import { measurePath } from './homePixiMotion';
import { HomeResultReportPopup } from './HomeResultReportPopup';
import { HomeHitlApprovalPopup } from './HomeHitlApprovalPopup';
import type { PendingHumanFeedbackRequest } from '../runs/HumanFeedbackDialog';

type HomePixiStageProps = {
  agents: AgentSceneModel[];
  edgeToEdge?: boolean;
  fullHeight?: boolean;
  isAnimationPaused?: boolean;
  resultReport?: {
    id: string;
    output: unknown;
    hasWarning: boolean;
  } | null;
  hitlRequest?: PendingHumanFeedbackRequest | null;
  isHitlBusy?: boolean;
  hitlSubmitError?: string | null;
  onSubmitHitl?: (outcome: 'approved' | 'rejected', feedback: string) => Promise<void>;
};

type PersistedViewport = {
  baseScale: number;
  zoom: number;
  x: number;
  y: number;
  width: number;
  height: number;
  hasPosition: boolean;
};

type TooltipState = {
  x: number;
  y: number;
  name: string;
  status: string;
  message: string;
};


const persistedSceneState = {
  viewport: {
    baseScale: 1,
    zoom: INITIAL_ZOOM,
    x: 0,
    y: 0,
    width: 0,
    height: 0,
    hasPosition: false,
  } as PersistedViewport,
  agents: new Map<string, PersistedAgent>(),
};

export function HomePixiStage({
  agents,
  edgeToEdge = false,
  fullHeight = false,
  isAnimationPaused = false,
  resultReport = null,
  hitlRequest = null,
  isHitlBusy = false,
  hitlSubmitError = null,
  onSubmitHitl,
}: HomePixiStageProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const agentsRef = useRef(agents);
  const isAnimationPausedRef = useRef(isAnimationPaused);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const [closedReportId, setClosedReportId] = useState<string | null>(null);

  agentsRef.current = agents;
  isAnimationPausedRef.current = isAnimationPaused;
  const isReportClosed = resultReport !== null && closedReportId === resultReport.id;

  useEffect(() => {
    if (import.meta.env.MODE === 'test') return;

    let destroyed = false;
    let cleanup = () => {};

    async function start() {
      const PIXI = await import('pixi.js');
      if (destroyed || !hostRef.current) return;

      const app = new PIXI.Application();
      await app.init({
        antialias: false,
        autoDensity: true,
        backgroundAlpha: 0,
        resolution: Math.min(window.devicePixelRatio || 1, 2),
        resizeTo: hostRef.current,
      });
      if (destroyed || !hostRef.current) {
        app.destroy(true);
        return;
      }

      hostRef.current.appendChild(app.canvas);
      app.canvas.style.display = 'block';
      app.canvas.style.width = '100%';
      app.canvas.style.height = '100%';
      app.canvas.style.cursor = 'grab';

      const assets = await loadHomePixiAssets(PIXI);
      if (destroyed) {
        app.destroy(true);
        return;
      }

      const stageBackground = new PIXI.Sprite(assets.stageBackgroundTexture);
      app.stage.addChild(stageBackground);

      const world = new PIXI.Container();
      app.stage.addChild(world);
      const viewport = persistedSceneState.viewport;
      const drag = {
        active: false,
        lastX: 0,
        lastY: 0,
      };

      const background = new PIXI.Sprite(assets.backgroundTexture);
      world.addChild(background);

      const depthLayer = new PIXI.Container();
      depthLayer.sortableChildren = true;
      world.addChild(depthLayer);

      DESKS.forEach((deskConfig) => {
        const desk = new PIXI.Sprite(assets.deskTexture);
        desk.label = deskConfig.id;
        desk.anchor.set(0.5, 0.72);
        desk.scale.set(deskConfig.scale);
        desk.rotation = deskConfig.rotation;
        desk.skew.set(deskConfig.skewX, deskConfig.skewY);
        desk.position.set(deskConfig.x, deskConfig.y);
        desk.zIndex = deskConfig.zIndex;
        depthLayer.addChild(desk);
      });

      const table = new PIXI.Sprite(assets.tableTexture);
      table.anchor.set(0.5, 0.66);
      table.scale.set(MEETING_TABLE.scale);
      table.rotation = TABLE_ALIGNMENT.rotation;
      table.skew.set(TABLE_ALIGNMENT.skewX, TABLE_ALIGNMENT.skewY);
      table.position.set(MEETING_TABLE.x, MEETING_TABLE.y);
      table.zIndex = MEETING_TABLE_Z_INDEX;
      depthLayer.addChild(table);

      assets.tablePartTextures.forEach((texture, index) => {
        const config = MEETING_TABLE_PARTS[index];
        const part = new PIXI.Sprite(texture);
        part.label = `meeting-table-${config.id}`;
        part.anchor.set(0.5, 0.66);
        part.scale.set(MEETING_TABLE.scale);
        part.rotation = TABLE_ALIGNMENT.rotation;
        part.skew.set(TABLE_ALIGNMENT.skewX, TABLE_ALIGNMENT.skewY);
        part.position.set(
          MEETING_TABLE.x +
            (config.sourceX + config.width * 0.5 - MEETING_TABLE_SOURCE_ANCHOR.x) * MEETING_TABLE.scale,
          MEETING_TABLE.y +
            (config.sourceY + config.height * 0.66 - MEETING_TABLE_SOURCE_ANCHOR.y) * MEETING_TABLE.scale,
        );
        part.zIndex = MEETING_TABLE_PART_Z_INDEX;
        depthLayer.addChild(part);
      });

      if (SHOW_MOCK_AGENT_COORDINATES) {
        MOCK_AGENT_COORDINATE_SPOTS.forEach((spot, index) => {
          const frames = assets.meetingAgentWalkingFrames[index % assets.meetingAgentWalkingFrames.length]?.[0] ?? [];
          const texture = frames[0];
          if (!texture) return;

          const marker = new PIXI.Container();
          marker.label = `mock-agent-coordinate-${index + 1}`;
          marker.position.set(spot.x, spot.y);
          marker.zIndex = spot.y;

          const sprite = new PIXI.Sprite(texture);
          sprite.anchor.set(0.5, 0.92);
          sprite.scale.set(index % 2 === 0 ? 0.36 : -0.36, 0.36);

          const label = new PIXI.Text({
            text: `${index + 1}: ${Math.round(spot.x)}, ${Math.round(spot.y)}`,
            style: {
              fill: 0xffffff,
              fontFamily: 'monospace',
              fontSize: 18,
              fontWeight: '700',
              stroke: { color: 0x1f2937, width: 4 },
            },
          });
          label.anchor.set(0.5, 1);
          label.position.set(0, -112);

          marker.addChild(sprite, label);
          depthLayer.addChild(marker);
        });
      }

      const members = new Map<string, RuntimeAgentMember>();

      function updateTooltipPosition(event: PointerEvent) {
        if (!hostRef.current) return;
        const rect = hostRef.current.getBoundingClientRect();
        const x = Math.min(rect.width - 24, Math.max(24, event.clientX - rect.left));
        const y = Math.min(rect.height - 24, Math.max(24, event.clientY - rect.top));
        setTooltip((current) => (current ? { ...current, x, y } : current));
      }

      function showAgentTooltip(agentId: string, event: PointerEvent) {
        if (!hostRef.current) return;
        const agent = agentsRef.current.find((candidate) => candidate.id === agentId);
        if (!agent) return;
        const rect = hostRef.current.getBoundingClientRect();
        const lastMessage = agent.lastMessage || 'Waiting for the next workflow event.';
        const role = agent.meta?.role ?? agent.name ?? 'Agent';
        const details = agent.meta?.details ?? '';
        const goal = agent.meta?.goal ?? '';
        // build tooltip message: show goal then last message
        const tooltipMessage = (goal ? `Goal: ${goal}\n` : '') + (details || lastMessage);
        setTooltip({
          x: event.clientX - rect.left,
          y: event.clientY - rect.top,
          name: role,
          status: agent.status,
          message: tooltipMessage,
        });
      }

      function drawAgent(agent: AgentSceneModel) {
        return createRuntimeAgentMember(PIXI, depthLayer, assets, agent, persistedSceneState.agents.get(agent.id), {
          showTooltip: showAgentTooltip,
          updateTooltipPosition,
          hideTooltip: () => setTooltip(null),
        });
      }

      const donePathLength = measurePath(DONE_AGENT_PATH);

      // Agents are created only from flow runtime events.

      function applyViewport() {
        const scale = viewport.baseScale * viewport.zoom;
        world.scale.set(scale);
        world.position.set(viewport.x, viewport.y);
      }

      function fitStageBackground() {
        const width = app.renderer.width;
        const height = app.renderer.height;
        const scale = Math.max(width / assets.stageBackgroundTexture.width, height / assets.stageBackgroundTexture.height);
        stageBackground.width = assets.stageBackgroundTexture.width * scale;
        stageBackground.height = assets.stageBackgroundTexture.height * scale;
        stageBackground.position.set((width - stageBackground.width) / 2, (height - stageBackground.height) / 2);
      }

      function centerScene() {
        const width = app.renderer.width;
        const height = app.renderer.height;
        fitStageBackground();
        const oldScale = viewport.baseScale * viewport.zoom;
        const previousCenter =
          viewport.hasPosition && oldScale > 0
            ? {
                x: (viewport.width / 2 - viewport.x) / oldScale,
                y: (viewport.height / 2 - viewport.y) / oldScale,
              }
            : { x: DESIGN_SIZE / 2, y: DESIGN_SIZE / 2 };

        viewport.baseScale = Math.min(width / DESIGN_SIZE, height / DESIGN_SIZE);
        const scale = viewport.baseScale * viewport.zoom;

        const centerIsOutsideScene =
          previousCenter.x < -DESIGN_SIZE * 0.1 ||
          previousCenter.x > DESIGN_SIZE * 1.1 ||
          previousCenter.y < -DESIGN_SIZE * 0.1 ||
          previousCenter.y > DESIGN_SIZE * 1.1;
        const nextCenter = centerIsOutsideScene ? { x: DESIGN_SIZE / 2, y: DESIGN_SIZE / 2 } : previousCenter;

        viewport.x = width / 2 - nextCenter.x * scale;
        viewport.y = height / 2 - nextCenter.y * scale;
        viewport.width = width;
        viewport.height = height;
        viewport.hasPosition = true;

        const visibleWorldBounds = {
          left: (0 - viewport.x) / scale,
          top: (0 - viewport.y) / scale,
          right: (width - viewport.x) / scale,
          bottom: (height - viewport.y) / scale,
        };
        const sceneIsVisible =
          visibleWorldBounds.right > 0 &&
          visibleWorldBounds.left < DESIGN_SIZE &&
          visibleWorldBounds.bottom > 0 &&
          visibleWorldBounds.top < DESIGN_SIZE;

        if (!Number.isFinite(viewport.x) || !Number.isFinite(viewport.y) || !sceneIsVisible) {
          viewport.x = (width - DESIGN_SIZE * scale) / 2;
          viewport.y = (height - DESIGN_SIZE * scale) / 2;
        }
        applyViewport();
        background.width = DESIGN_SIZE;
        background.height = DESIGN_SIZE;
        background.position.set(0, 0);
      }

      const resizeObserver = new ResizeObserver(centerScene);
      resizeObserver.observe(hostRef.current);
      centerScene();

      function handleWheel(event: WheelEvent) {
        event.preventDefault();
        if (!hostRef.current) return;
        const rect = hostRef.current.getBoundingClientRect();
        const pointerX = event.clientX - rect.left;
        const pointerY = event.clientY - rect.top;
        const oldScale = viewport.baseScale * viewport.zoom;
        const worldX = (pointerX - viewport.x) / oldScale;
        const worldY = (pointerY - viewport.y) / oldScale;
        const zoomFactor = event.deltaY < 0 ? 1.12 : 0.89;
        viewport.zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, viewport.zoom * zoomFactor));
        const nextScale = viewport.baseScale * viewport.zoom;
        viewport.x = pointerX - worldX * nextScale;
        viewport.y = pointerY - worldY * nextScale;
        applyViewport();
      }

      function handlePointerDown(event: PointerEvent) {
        drag.active = true;
        drag.lastX = event.clientX;
        drag.lastY = event.clientY;
        app.canvas.style.cursor = 'grabbing';
        app.canvas.setPointerCapture(event.pointerId);
      }

      function handlePointerMove(event: PointerEvent) {
        if (!drag.active) return;
        viewport.x += event.clientX - drag.lastX;
        viewport.y += event.clientY - drag.lastY;
        drag.lastX = event.clientX;
        drag.lastY = event.clientY;
        applyViewport();
      }

      function stopDrag(event: PointerEvent) {
        drag.active = false;
        app.canvas.style.cursor = 'grab';
        if (app.canvas.hasPointerCapture(event.pointerId)) {
          app.canvas.releasePointerCapture(event.pointerId);
        }
      }

      hostRef.current.addEventListener('wheel', handleWheel, { passive: false });
      app.canvas.addEventListener('pointerdown', handlePointerDown);
      app.canvas.addEventListener('pointermove', handlePointerMove);
      app.canvas.addEventListener('pointerup', stopDrag);
      app.canvas.addEventListener('pointercancel', stopDrag);
      app.canvas.addEventListener('pointerleave', stopDrag);

      const syncAgents = () => {
        const nextAgents = agentsRef.current;
        nextAgents.forEach((agent) => {
          if (!members.has(agent.id)) members.set(agent.id, drawAgent(agent));
          const member = members.get(agent.id);
          if (!member) return;
          member.status = agent.status;
        });

        for (const [id, member] of members) {
          if (!nextAgents.some((agent) => agent.id === id)) {
            member.root.destroy({ children: true });
            members.delete(id);
          }
        }
      };

      syncAgents();
      app.ticker.add((ticker) => {
        syncAgents();

        if (isAnimationPausedRef.current) {
          members.forEach((member) => {
            if (member.sprite.playing) member.sprite.stop();
          });
          return;
        }

        agentsRef.current.forEach((agent, index) => {
          const member = members.get(agent.id);
          if (!member) return;
          updateRuntimeAgentMember(member, agent, index, assets, donePathLength, ticker.deltaTime);
          persistedSceneState.agents.set(agent.id, {
            x: member.root.x,
            y: member.root.y,
            bob: member.bob,
            row: member.row,
          });
        });
      });

      cleanup = () => {
        resizeObserver.disconnect();
        hostRef.current?.removeEventListener('wheel', handleWheel);
        app.canvas.removeEventListener('pointerdown', handlePointerDown);
        app.canvas.removeEventListener('pointermove', handlePointerMove);
        app.canvas.removeEventListener('pointerup', stopDrag);
        app.canvas.removeEventListener('pointercancel', stopDrag);
        app.canvas.removeEventListener('pointerleave', stopDrag);
        app.destroy(true, { children: true, texture: false });
      };
    }

    start();

    return () => {
      destroyed = true;
      cleanup();
    };
  }, []);

  return (
    <div
      className={
        edgeToEdge
          ? `relative ${fullHeight ? 'h-full' : 'h-[min(70vh,820px)]'} w-full min-w-full self-stretch overflow-hidden bg-[#F5E6D3]`
          : `relative ${fullHeight ? 'h-full' : 'h-[min(68vh,760px)]'} w-full overflow-hidden rounded-md bg-[#F5E6D3]`
      }
      style={{ minHeight: fullHeight ? undefined : undefined }}
    >
      <div ref={hostRef} className="absolute inset-0" aria-label="Workflow agent animation scene" />
      {hitlRequest && onSubmitHitl ? (
        <HomeHitlApprovalPopup
          pendingRequest={hitlRequest}
          isBusy={isHitlBusy}
          submitError={hitlSubmitError}
          onSubmit={onSubmitHitl}
        />
      ) : null}
      {resultReport && !isReportClosed ? (
        <HomeResultReportPopup
          output={resultReport.output}
          hasWarning={resultReport.hasWarning}
          onClose={() => setClosedReportId(resultReport.id)}
        />
      ) : null}
      {tooltip ? (
        <div
          className="pointer-events-none absolute z-10 max-w-64 rounded-md border border-stone-700 bg-stone-950/90 px-3 py-2 text-left shadow-lg"
          style={{
            left: tooltip.x,
            top: tooltip.y,
            transform: 'translate(-50%, calc(-100% - 14px))',
          }}
          role="tooltip"
        >
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-semibold text-stone-50">{tooltip.name}</p>
            <p className="text-[11px] uppercase text-cyan-200">{tooltip.status}</p>
          </div>
          <p className="mt-1 line-clamp-3 text-xs leading-5 text-stone-200">{tooltip.message}</p>
        </div>
      ) : null}
    </div>
  );
}
