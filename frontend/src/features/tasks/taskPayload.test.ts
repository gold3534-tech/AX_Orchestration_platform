import { describe, expect, it } from 'vitest';
import { asOutputSchemaFields } from './hooks';

describe('task payload mapping', () => {
  it('accepts backend schema fields with nullable or omitted defaults', () => {
    expect(
      asOutputSchemaFields([
        { name: 'topic', type: 'str' },
        { name: 'score', type: 'int', description: null, required: false },
        { name: 'ignored', type: 'uuid' },
      ]),
    ).toEqual([
      { name: 'topic', type: 'str', description: '', required: true },
      { name: 'score', type: 'int', description: '', required: false },
    ]);
  });
});
