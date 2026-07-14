import type { ProcessingStatus } from '../../types/agent';

const STEPS: Array<{ status: ProcessingStatus; label: string }> = [
  { status: 'uploading', label: 'Upload' },
  { status: 'extracting', label: 'Extract' },
  { status: 'routing', label: 'Route' },
  { status: 'generating', label: 'Generate' },
  { status: 'complete', label: 'Complete' },
];

export function ProcessingSteps({ status }: { status: ProcessingStatus }) {
  const current = status === 'error' ? -1 : STEPS.findIndex(step => step.status === status);
  if (status === 'idle') return null;
  return (
    <div className="glass-panel p-4">
      <div className="flex items-center">
        {STEPS.map((step, index) => {
          const done = current >= index || status === 'complete';
          const active = current === index;
          return (
            <div key={step.status} className="flex items-center flex-1 last:flex-none">
              <div className="flex flex-col items-center gap-1">
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold ${done ? 'bg-hemaguide-600 text-white' : 'bg-slate-200 text-slate-500'} ${active ? 'ring-4 ring-hemaguide-100' : ''}`}>
                  {done && !active ? '✓' : index + 1}
                </div>
                <span className="text-[11px] text-slate-500">{step.label}</span>
              </div>
              {index < STEPS.length - 1 && <div className={`h-0.5 flex-1 mx-2 mb-5 ${current > index ? 'bg-hemaguide-500' : 'bg-slate-200'}`} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}
