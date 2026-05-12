import {
  BACKGROUND_URL,
  DESK_URL,
  MEETING_AGENT_LANDING_FRAME,
  MEETING_AGENT_LANDING_URLS,
  MEETING_AGENT_TALKING_FRAME,
  MEETING_AGENT_TALKING_URLS,
  MEETING_AGENT_WALKING_FRAME,
  MEETING_AGENT_WALKING_URLS,
  MEETING_AGENT_WORKING_FRAME,
  MEETING_AGENT_WORKING_URLS,
  STAGE_BACKGROUND_URL,
  TABLE_PART_URLS,
  TABLE_URL,
} from './homePixiConfig';

type PixiModule = typeof import('pixi.js');
type PixiTexture = InstanceType<PixiModule['Texture']>;

type SpriteFrame = {
  width: number;
  height: number;
  columns: number;
  rows: number;
};

function textureFrames(PIXI: PixiModule, texture: PixiTexture, frame: SpriteFrame) {
  return Array.from({ length: frame.rows }, (_, row) =>
    Array.from(
      { length: frame.columns },
      (_, column) =>
        new PIXI.Texture({
          source: texture.source,
          frame: new PIXI.Rectangle(column * frame.width, row * frame.height, frame.width, frame.height),
        }),
    ),
  );
}

async function loadOptionalTexture(PIXI: PixiModule, url: string) {
  try {
    return (await PIXI.Assets.load(url)) as PixiTexture;
  } catch {
    return null;
  }
}

export async function loadHomePixiAssets(PIXI: PixiModule) {
  const [
    stageBackgroundTexture,
    backgroundTexture,
    tableTexture,
    tablePartTextures,
    deskTexture,
    meetingAgentLandingTextures,
    meetingAgentTalkingTextures,
    meetingAgentWalkingTextures,
    meetingAgentWorkingTextures,
  ] = await Promise.all([
    PIXI.Assets.load(STAGE_BACKGROUND_URL) as Promise<PixiTexture>,
    PIXI.Assets.load(BACKGROUND_URL) as Promise<PixiTexture>,
    PIXI.Assets.load(TABLE_URL) as Promise<PixiTexture>,
    Promise.all(TABLE_PART_URLS.map((url) => PIXI.Assets.load(url))) as Promise<PixiTexture[]>,
    PIXI.Assets.load(DESK_URL) as Promise<PixiTexture>,
    Promise.all(MEETING_AGENT_LANDING_URLS.map((url) => loadOptionalTexture(PIXI, url))),
    Promise.all(MEETING_AGENT_TALKING_URLS.map((url) => loadOptionalTexture(PIXI, url))),
    Promise.all(MEETING_AGENT_WALKING_URLS.map((url) => loadOptionalTexture(PIXI, url))),
    Promise.all(MEETING_AGENT_WORKING_URLS.map((url) => loadOptionalTexture(PIXI, url))),
  ]);

  return {
    stageBackgroundTexture,
    backgroundTexture,
    tableTexture,
    tablePartTextures,
    deskTexture,
    meetingAgentLandingFrames: meetingAgentLandingTextures.map((texture) =>
      texture ? textureFrames(PIXI, texture, MEETING_AGENT_LANDING_FRAME).flat() : [],
    ),
    meetingAgentTalkingFrames: meetingAgentTalkingTextures.map((texture) =>
      texture ? textureFrames(PIXI, texture, MEETING_AGENT_TALKING_FRAME).flat() : [],
    ),
    meetingAgentWalkingFrames: meetingAgentWalkingTextures.map((texture) =>
      texture ? textureFrames(PIXI, texture, MEETING_AGENT_WALKING_FRAME) : [],
    ),
    meetingAgentWorkingFrames: meetingAgentWorkingTextures.map((texture) =>
      texture ? textureFrames(PIXI, texture, MEETING_AGENT_WORKING_FRAME).flat() : [],
    ),
  };
}

export type HomePixiAssets = Awaited<ReturnType<typeof loadHomePixiAssets>>;
