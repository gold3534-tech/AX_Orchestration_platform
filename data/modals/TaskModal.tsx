import React from 'react';
import { motion } from 'motion/react';
import { X, ClipboardList, Zap, ShieldCheck, FileOutput, Settings2, Sparkles, Layers, Wrench, FileCode, Bot } from 'lucide-react';
import { 
  Section, 
  FieldGroup, 
  Toggle, 
  NumberInput, 
  TextInput,
  SchemaBuilder,
  MultiSelector
} from '../ui/ConfigUI';
import { TaskAttributes } from '../../types';
import { cleanPayload } from '../../utils/dataUtils';
import { fetchOptions, Options } from '../../services/apiService';

export default function TaskModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const [options, setOptions] = React.useState<Options | null>(null);

  React.useEffect(() => {
    if (isOpen) {
      fetchOptions().then(setOptions);
    }
  }, [isOpen]);

  const [data, setData] = React.useState<TaskAttributes>({
    // agents, tasks attributes는 Canvas에서 값을 받을 것
    name: '',
    description:'',
    expected_output: '',
    output_type: 'Raw'
  });

  const handleSave = () => {
    const cleaned = cleanPayload(data);
    console.log('Saving Task Payload (Cleaned):', cleaned);
    onClose();
  };

  const handlePresetSelect = (presetName: string) => {
    const preset = options?.presets.find(p => p.name === presetName);
    if (!preset) return;

    const token = preset.token;
    
    // 1. Description injection
    const newDesc = data.description ? `${data.description} ${token}` : token;

    // 2. Output handling
    let newExpected = data.expected_output;
    let newFields = [...(data.output_schema_fields || [])];

    if (data.output_type === 'Raw') {
      newExpected = newExpected ? `${newExpected} ${token}` : token;
    } else {
      // For JSON/Pydantic, inject into field descriptions if fields exist
      if (newFields.length > 0) {
        newFields = newFields.map(f => ({
          ...f,
          description: f.description ? `${f.description} ${token}` : token
        }));
      }
    }

    setData({
      ...data,
      description: newDesc,
      expected_output: newExpected,
      output_schema_fields: newFields
    });
  };

  const outputTypeOptions = ['Raw', 'Output JSON', 'Output Pydantic'];

  const [selectedTools, setSelectedTools] = React.useState<string[] | undefined>(undefined);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="absolute inset-0 bg-zinc-950/40 backdrop-blur-sm" 
      />
      
      <motion.div
        initial={{ y: 20, opacity: 0, scale: 0.98 }}
        animate={{ y: 0, opacity: 1, scale: 1 }}
        exit={{ y: 20, opacity: 0, scale: 0.98 }}
        className="relative w-full max-w-[1300px] h-[85vh] bg-white dark:bg-zinc-950 rounded-xl shadow-2xl flex flex-col overflow-hidden border border-zinc-200 dark:border-zinc-800"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-100 dark:border-zinc-900 bg-zinc-50/50 dark:bg-zinc-900/50">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-indigo-100 dark:bg-indigo-900/30 rounded-lg">
              <ClipboardList className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">Configure Task</h2>
              <p className="text-[11px] text-zinc-500 uppercase font-medium tracking-tight">Task System Reference: TASK_NEW_ID</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors">
            <X className="w-5 h-5 text-zinc-400" />
          </button>
        </div>

        {/* Content - 3 Column Layout */}
        <div className="flex-1 flex overflow-hidden">
          
          {/* Column 1: Task Definition (Left) */}
          <div className="flex-[0.85] overflow-y-auto p-6 border-r border-zinc-100 dark:border-zinc-900 space-y-6">
            <div className="space-y-4">
              <h3 className="text-sm font-bold text-zinc-400 uppercase tracking-widest flex items-center gap-2">
                <Sparkles className="w-3.5 h-3.5" /> Task Definition
              </h3>
              <div className="w-1/2">
                <FieldGroup label="Name">
                  <TextInput value={data.name} onChange={(val) => setData({...data, name: val})} placeholder="Enter task name..." />
                </FieldGroup>
              </div>
              <FieldGroup label="Description">
                <TextInput value={data.description} onChange={(val) => setData({...data, description: val})} multiline placeholder="Provide detailed instructions for the agent..." />
              </FieldGroup>
              
              <FieldGroup label="Guardrails" helperText="Specific instructions for validation.">
                 <TextInput 
                    value={data.guardrail_config_str} 
                    onChange={(val) => setData({...data, guardrail_config_str: val})} 
                    multiline 
                    placeholder="e.g. Ensure the output does not contain PII data."
                 />
              </FieldGroup>

              <div className="pt-4">
                <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-tight flex items-center gap-2 mb-4">
                  <Wrench className="w-3 h-3" /> Tools
                </h3>
                <MultiSelector 
                  options={options?.tools || []}
                  selected={selectedTools}
                  onAdd={(val) => setSelectedTools([...(selectedTools || []), val])}
                  onRemove={(item) => setSelectedTools((selectedTools || []).filter(i => i !== item))}
                  placeholder="Select a tool to add..."
                />
              </div>
            </div>
          </div>

          {/* Column 2: Output Structure (Center) */}
          <div className="flex-[0.95] overflow-y-auto p-6 border-r border-zinc-100 dark:border-zinc-900 space-y-6 bg-zinc-50/20 dark:bg-zinc-950/20">
             <div className="space-y-4">
                <h3 className="text-sm font-bold text-zinc-400 uppercase tracking-widest flex items-center gap-2">
                  <FileCode className="w-3.5 h-3.5" /> EXPECTED OUTPUT
                </h3>
                
                <FieldGroup label="Output Type">
                  <select 
                    value={data.output_type}
                    onChange={(e) => setData({...data, output_type: e.target.value as any})}
                    className="w-full h-9 px-3 text-sm bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-lg outline-none focus:ring-1 focus:ring-indigo-500 font-medium"
                  >
                    {outputTypeOptions.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                  </select>
                </FieldGroup>

                {data.output_type === 'Raw' ? (
                  <FieldGroup label="Structure Instructions" helperText="Define the format in text.">
                    <TextInput 
                      value={data.expected_output} 
                      onChange={(val) => setData({...data, expected_output: val})} 
                      multiline 
                      placeholder="Specify the raw text structure (e.g. Bullet points, CSV, etc.)" 
                    />
                  </FieldGroup>
                ) : (
                  <div className="space-y-6">
                    <SchemaBuilder 
                      fields={data.output_schema_fields || []} 
                      onChange={(fields) => setData({...data, output_schema_fields: fields})} 
                    />
                    
                    <div className="pt-6 border-t border-zinc-200 dark:border-zinc-800">
                       <FieldGroup label="Pydantic Class" helperText="Advanced server validation mapping.">
                         <TextInput value={data.output_pydantic_schema} onChange={(val) => setData({...data, output_pydantic_schema: val})} placeholder="e.g. BaseModel" />
                       </FieldGroup>
                    </div>
                  </div>
                )}
             </div>
          </div>

          {/* Column 3: Settings Sidebar (Right) */}
          <div className="w-[340px] overflow-y-auto bg-zinc-50/50 dark:bg-zinc-950/30">
            <Section title="REPRESENTATIVE" icon={Bot} defaultOpen={true}>
              <div className="mb-4 p-3 bg-red-500/10 border border-red-500/50 rounded-lg">
                <p className="text-[11px] text-red-600 dark:text-red-400 font-bold leading-tight">
                  If you set the workflow to a <span className="underline">Sequential Process</span>, agent assignment is required. Otherwise, the flow will NOT RUN.
                </p>
              </div>
              <FieldGroup label="Agent" helperText="The agent responsible for this task.">
                <select 
                  value={data.agent_id || ''}
                  onChange={(e) => setData({...data, agent_id: e.target.value})}
                  className="w-full h-9 px-3 text-sm bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-lg outline-none focus:ring-1 focus:ring-indigo-500 font-medium appearance-none"
                  style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%239CA3AF'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E")`, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 0.75rem center', backgroundSize: '1rem' }}
                >
                  <option value="">No Agent Assigned</option>
                  {options?.agents?.map(name => <option key={name} value={name}>{name}</option>)}
                </select>
              </FieldGroup>
            </Section>

            <Section title="INPUT PRESET" icon={Sparkles} defaultOpen={false}>
              <FieldGroup label="Presets" helperText="Inject dynamic tokens into fields.">
                <select 
                  value=""
                  onChange={(e) => handlePresetSelect(e.target.value)}
                  className="w-full h-9 px-3 text-sm bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-lg outline-none focus:ring-1 focus:ring-indigo-500 font-medium appearance-none"
                  style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%239CA3AF'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E")`, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 0.75rem center', backgroundSize: '1rem' }}
                >
                  <option value="" disabled>Select a preset...</option>
                  {options?.presets?.map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
                </select>
              </FieldGroup>
            </Section>

            <Section title="Execution" icon={Zap} defaultOpen={false}>
              <Toggle label="Async Execution" value={data.async_execution} onChange={(val) => setData({...data, async_execution: val})} />
              <Toggle label="Human Input" value={data.human_input} onChange={(val) => setData({...data, human_input: val})} />
            </Section>

            <Section title="File Settings" icon={FileOutput} defaultOpen={false}>
              <div className="space-y-4">
                <Toggle 
                  label="Markdown Output" 
                  description="Required for .md report generation"
                  value={data.markdown} 
                  onChange={(val) => setData({...data, markdown: val})} 
                />
                <Toggle 
                  label="Create Directory" 
                  description="Required for directory structure / .json"
                  value={data.create_directory} 
                  onChange={(val) => setData({...data, create_directory: val})} 
                />

                {(data.markdown || data.create_directory) && (
                  <div className="pt-2 border-t border-zinc-100 dark:border-zinc-900 mt-2">
                    <FieldGroup 
                      label={data.markdown ? "Output File Path (.md)" : "Output File Path (.json)"}
                      helperText={data.create_directory ? "Directory will be created if it doesn't exist." : ""}
                    >
                      <TextInput 
                        value={data.output_file} 
                        onChange={(val) => setData({...data, output_file: val})} 
                        placeholder={data.markdown ? "e.g. reports/analysis.md" : "e.g. data/results.json"} 
                      />
                    </FieldGroup>
                  </div>
                )}
              </div>
            </Section>

            <Section title="Advanced" icon={Settings2} defaultOpen={false}>
              <div className="space-y-4">
                 <h3 className="text-[11px] font-bold text-zinc-500 uppercase tracking-tight flex items-center gap-2">
                   <Layers className="w-3 h-3" /> CrewAI Context
                 </h3>
                  <MultiSelector 
                    options={options?.tasks || []}
                    selected={data.allow_crewai_context_tasks}
                    onAdd={(val) => setData({...data, allow_crewai_context_tasks: [...(data.allow_crewai_context_tasks || []), val]})}
                    onRemove={(item) => setData({...data, allow_crewai_context_tasks: (data.allow_crewai_context_tasks || []).filter(i => i !== item)})}
                    placeholder="Select contexts..."
                 />
              </div>
            </Section>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-zinc-100 dark:border-zinc-900 flex items-center justify-between bg-zinc-50/50 dark:bg-zinc-950">
          <p className="text-[11px] text-zinc-500 italic font-medium tracking-tight uppercase">Task snapshots are immutable once deployed to runtime.</p>
          <div className="flex items-center gap-3">
            <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors">
              Cancel
            </button>
            <button onClick={handleSave} className="px-6 py-2 text-sm font-semibold bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 shadow-lg shadow-indigo-600/20 transition-all">
              Save Task
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
