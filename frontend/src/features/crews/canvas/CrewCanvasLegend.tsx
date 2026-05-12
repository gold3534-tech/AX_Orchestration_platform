export function CrewCanvasLegend() {
  return (
    <div className="absolute right-3 top-3 z-10 rounded-md border-2 border-[#7a5739] bg-[#fff6df]/95 px-3 py-2 text-xs font-bold shadow-[3px_3px_0_#7a5739]">
      <p className="text-red-600">🔴: Assign a agent</p>
      <p className="mt-1 text-orange-600">🟠: Context Transfer</p>
      <p className="mt-1 text-green-600">🟢: Task Sequence</p>
    </div>
  );
}
