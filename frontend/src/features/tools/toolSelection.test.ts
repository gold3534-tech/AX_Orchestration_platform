import { describe, expect, it } from 'vitest';
import { diffToolSelections } from './toolSelection';

describe('diffToolSelections', () => {
  it('returns tools to attach and remove', () => {
    expect(diffToolSelections(['crewai.file_read', 'crewai.serper_dev'], ['crewai.serper_dev', 'crewai.dalle'])).toEqual({
      attach: ['crewai.dalle'],
      remove: ['crewai.file_read'],
    });
  });
});
