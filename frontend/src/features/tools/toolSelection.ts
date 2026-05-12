export function diffToolSelections(previous: string[], next: string[]) {
  return {
    attach: next.filter((toolKey) => !previous.includes(toolKey)),
    remove: previous.filter((toolKey) => !next.includes(toolKey)),
  };
}
