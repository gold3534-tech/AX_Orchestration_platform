import { useEffect, useState } from 'react';

type ToolPickerProps = {
  tools: string[];
  selectedTools: string[];
  onChange: (tools: string[]) => void;
  emptyText?: string;
};

export function ToolPicker({
  tools,
  selectedTools,
  onChange,
  emptyText = 'There are no available tools yet.',
}: ToolPickerProps) {
  const availableTools = tools.filter((tool) => !selectedTools.includes(tool));
  const selectedToolSet = new Set(selectedTools);
  const [toolToAdd, setToolToAdd] = useState('');

  useEffect(() => {
    if (toolToAdd && availableTools.includes(toolToAdd)) return;
    setToolToAdd(availableTools[0] ?? '');
  }, [availableTools, toolToAdd]);

  function addTool(toolKey: string) {
    if (!toolKey || selectedToolSet.has(toolKey)) return;
    onChange([...selectedTools, toolKey]);
  }

  function removeTool(toolKey: string) {
    onChange(selectedTools.filter((selectedTool) => selectedTool !== toolKey));
  }

  return (
    <fieldset className="min-w-0 max-w-full overflow-hidden rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-4 py-4">
      <legend className="px-1 text-sm font-bold text-[#22170f]">Tools</legend>
      <div className="mt-4 flex min-w-0 flex-col gap-3 sm:flex-row">
        <select
          aria-label="Tool to add"
          value={toolToAdd}
          onChange={(event) => setToolToAdd(event.target.value)}
          disabled={availableTools.length === 0}
          className="min-w-0 flex-1 truncate rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-4 py-3 text-stone-950 disabled:opacity-60"
        >
          <option value="">Select a tool</option>
          {availableTools.map((tool) => (
            <option key={tool} value={tool}>
              {tool}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => addTool(toolToAdd)}
          disabled={!toolToAdd}
          className="pixel-button shrink-0 border-[#7a5739] bg-[#fffaf0] px-4 py-2 text-sm font-bold text-[#22170f] hover:bg-[#ffe6b3] disabled:cursor-not-allowed disabled:opacity-50"
        >
          Add tool
        </button>
      </div>

      {selectedTools.length > 0 ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {selectedTools.map((tool) => (
            <span
              key={tool}
              className="inline-flex max-w-full items-center gap-2 rounded border border-[#ef8b2c] bg-[#ffe6b3] px-3 py-1 text-sm font-semibold text-amber-950"
            >
              <span className="truncate">{tool}</span>
              <button
                type="button"
                onClick={() => removeTool(tool)}
                aria-label={`Remove ${tool}`}
                className="rounded border border-amber-500 px-2 text-xs text-amber-900 hover:bg-amber-100"
              >
                Remove
              </button>
            </span>
          ))}
        </div>
      ) : (
        <div className="mt-4 min-w-0 rounded-md border-2 border-dashed border-[#7a5739] bg-[#fff6df] px-4 py-6 text-sm text-stone-500">
          {tools.length === 0 ? emptyText : 'No tools added yet.'}
        </div>
      )}
    </fieldset>
  );
}
