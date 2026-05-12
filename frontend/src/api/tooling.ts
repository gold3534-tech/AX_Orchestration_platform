import type { components } from '../types/api.generated';
import { client } from './client';

type ToolCatalogCreate = components['schemas']['ToolCatalogCreate'];
type SkillCatalogCreate = components['schemas']['SkillCatalogCreate'];
type VersionToolAttachCreate = components['schemas']['VersionToolAttachCreate'];
type VersionToolAttachmentUpdate = components['schemas']['VersionToolAttachmentUpdate'];
type VersionSkillAttachCreate = components['schemas']['VersionSkillAttachCreate'];

export function getToolCatalog() {
  return client.GET('/api/tool-catalog');
}

export function getToolCatalogEntry(toolKey: string) {
  return client.GET('/api/tool-catalog/{tool_key}', {
    params: {
      path: {
        tool_key: toolKey,
      },
    },
  });
}

export function createToolCatalog(body: ToolCatalogCreate) {
  return client.POST('/api/tool-catalog', { body });
}

export function getSkillCatalog() {
  return client.GET('/api/skill-catalog');
}

export function createSkillCatalog(body: SkillCatalogCreate) {
  return client.POST('/api/skill-catalog', { body });
}

export function listAttachedTools(versionId: string) {
  return client.GET('/api/versions/{version_id}/tools', {
    params: {
      path: {
        version_id: versionId,
      },
    },
  });
}

export function attachTool(versionId: string, body: VersionToolAttachCreate) {
  return client.POST('/api/versions/{version_id}/tools', {
    params: {
      path: {
        version_id: versionId,
      },
    },
    body,
  });
}

export function updateAttachedTool(versionId: string, toolKey: string, body: VersionToolAttachmentUpdate) {
  return client.PATCH('/api/versions/{version_id}/tools/{tool_key}', {
    params: {
      path: {
        version_id: versionId,
        tool_key: toolKey,
      },
    },
    body,
  });
}

export function deleteAttachedTool(versionId: string, toolKey: string) {
  return client.DELETE('/api/versions/{version_id}/tools/{tool_key}', {
    params: {
      path: {
        version_id: versionId,
        tool_key: toolKey,
      },
    },
  });
}

export function listAttachedSkills(versionId: string) {
  return client.GET('/api/versions/{version_id}/skills', {
    params: {
      path: {
        version_id: versionId,
      },
    },
  });
}

export function attachSkill(versionId: string, body: VersionSkillAttachCreate) {
  return client.POST('/api/versions/{version_id}/skills', {
    params: {
      path: {
        version_id: versionId,
      },
    },
    body,
  });
}
