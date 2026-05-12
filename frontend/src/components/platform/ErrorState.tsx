type ErrorStateProps = {
  message: string;
};

export function ErrorState({ message }: ErrorStateProps) {
  return (
    <div className="rounded-2xl border border-rose-900 bg-rose-950/40 p-6 text-sm text-rose-200">
      {message}
    </div>
  );
}
