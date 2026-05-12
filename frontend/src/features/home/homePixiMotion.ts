import type { Point } from './homePixiConfig';

export function measurePath(points: readonly Point[]) {
  return points.slice(1).reduce((total, point, index) => {
    const previous = points[index];
    return total + Math.hypot(point.x - previous.x, point.y - previous.y);
  }, 0);
}

export function pointOnPath(points: readonly Point[], distance: number) {
  let remaining = distance;
  for (let index = 1; index < points.length; index += 1) {
    const previous = points[index - 1];
    const next = points[index];
    const segmentLength = Math.hypot(next.x - previous.x, next.y - previous.y);
    if (remaining <= segmentLength) {
      const progress = segmentLength === 0 ? 0 : remaining / segmentLength;
      return {
        x: previous.x + (next.x - previous.x) * progress,
        y: previous.y + (next.y - previous.y) * progress,
      };
    }
    remaining -= segmentLength;
  }
  return points[points.length - 1];
}

export function walkDirectionForDelta(dx: number, dy: number, scale: number) {
  const isRight = dx >= 0;
  const isDown = dy >= 0;
  const row = isDown ? 0 : 1;
  const flipX = isRight !== isDown;
  return {
    row,
    scaleX: flipX ? -scale : scale,
  };
}

export function closestPointIndex(points: readonly Point[], target: Point) {
  let closestIndex = 0;
  let closestDistance = Number.POSITIVE_INFINITY;
  points.forEach((point, index) => {
    const distance = Math.hypot(point.x - target.x, point.y - target.y);
    if (distance < closestDistance) {
      closestIndex = index;
      closestDistance = distance;
    }
  });
  return { index: closestIndex, distance: closestDistance };
}

export function nextRouteWaypoint(
  route: readonly Point[],
  current: Point,
  destination: Point,
  visitedIndexes: Set<number>,
  options: { routeSnapDistance?: number; destinationDistance?: number } = {},
) {
  if (route.length === 0) return destination;

  const routeSnapDistance = options.routeSnapDistance ?? 12;
  const destinationDistance = options.destinationDistance ?? 90;
  const currentToDestination = Math.hypot(destination.x - current.x, destination.y - current.y);
  if (currentToDestination <= destinationDistance) return destination;

  const currentNode = closestPointIndex(route, current);
  const destinationNode = closestPointIndex(route, destination);
  if (currentNode.distance <= routeSnapDistance) {
    visitedIndexes.add(currentNode.index);
  }

  const direction = destinationNode.index >= currentNode.index ? 1 : -1;
  const firstIndex = currentNode.distance <= routeSnapDistance ? currentNode.index + direction : currentNode.index;
  const candidates: Array<{ index: number; distance: number }> = [];
  for (
    let index = firstIndex;
    direction > 0 ? index <= destinationNode.index : index >= destinationNode.index;
    index += direction
  ) {
    if (index < 0 || index >= route.length || visitedIndexes.has(index)) continue;
    const point = route[index];
    candidates.push({ index, distance: Math.hypot(point.x - current.x, point.y - current.y) });
  }

  candidates.sort((a, b) => a.distance - b.distance);
  const nextIndex = candidates[0]?.index;
  return nextIndex === undefined ? destination : route[nextIndex];
}
