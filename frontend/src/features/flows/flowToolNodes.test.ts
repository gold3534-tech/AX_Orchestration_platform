import { describe, expect, it } from 'vitest';
import { getCrewStepSummaries } from './canvas/flowCanvasHelpers';

describe('Flow tool summaries', () => {
  it('reads agent and task effective tools from a published crew runtime snapshot', () => {
    const summaries = getCrewStepSummaries({
      runtime_crew: { task_version_ids: ['task-version-1'] },
      runtime_tasks: { 'task-version-1': { task_name: 'Generate Image' } },
      runtime_agents: { 'agent-version-1': { agent_name: 'WebSearch' } },
      task_agent_links: { 'task-version-1': 'agent-version-1' },
      agent_tool_links: { 'agent-version-1': ['crewai.serper_dev'] },
      task_tool_links: { 'task-version-1': ['crewai.dalle'] },
      runtime_tools: {
        'crewai.serper_dev': { name: 'Serper Dev Search' },
        'crewai.dalle': { name: 'DALL-E Tool' },
      },
    });

    expect(summaries[0]).toMatchObject({
      toolKeys: ['crewai.serper_dev', 'crewai.dalle'],
      toolNames: ['Serper Dev Search', 'DALL-E Tool'],
      agentToolNames: ['Serper Dev Search'],
      taskToolNames: ['Serper Dev Search', 'DALL-E Tool'],
    });
  });
});
