import { describe, expect, it } from 'vitest';
import { walkDirectionForDelta } from '../../src/features/home/homePixiMotion';

describe('home pixi walking direction', () => {
  it.each([
    { dx: 1, dy: 1, row: 0, scaleX: 0.45 },
    { dx: 1, dy: -1, row: 1, scaleX: -0.45 },
    { dx: -1, dy: 1, row: 0, scaleX: -0.45 },
    { dx: -1, dy: -1, row: 1, scaleX: 0.45 },
  ])('selects the expected row and flip for dx=$dx dy=$dy', ({ dx, dy, row, scaleX }) => {
    expect(walkDirectionForDelta(dx, dy, 0.45)).toEqual({ row, scaleX });
  });
});
