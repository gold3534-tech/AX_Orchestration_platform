import React from 'react';
import { motion } from 'motion/react';
import { X, Bot, Zap, Cpu, Clock, Settings2, Sparkles, DollarSign, Wrench, BookOpen } from 'lucide-react';
import { 
  Section, 
  FieldGroup, 
  Toggle, 
  NumberInput, 
  TextInput,
  SelectInput,
  MultiSelector
} from '../ui/ConfigUI';
import { AgentAttributes } from '../../types';
import { cleanPayload } from '../../utils/dataUtils';
import { fetchOptions, Options } from '../../services/apiService';

export default function AgentModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const [options, setOptions] = React.useState<Options | null>(null);

  React.useEffect(() => {
    if (isOpen) {
      fetchOptions().then(setOptions);
    }
  }, [isOpen]);

  const [data, setData] = React.useState<AgentAttributes>({
    role: '',
    goal: '',
    backstory: ''
    // 나머지는 아예 선언 안 하면 자동으로 undefined 취급!
  });

  const handleSave = () => {
    const cleaned = cleanPayload(data);
    console.log('Saving Agent Payload (Cleaned):', cleaned);
    onClose();
  };

  const [selectedTools, setSelectedTools] = React.useState<string[] | undefined>(undefined);
  const [selectedKnowledge, setSelectedKnowledge] = React.useState<string[] | undefined>(undefined);

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
        className="relative w-full max-w-[1000px] h-[85vh] bg-white dark:bg-zinc-950 rounded-xl shadow-2xl flex flex-col overflow-hidden border border-zinc-200 dark:border-zinc-800"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-100 dark:border-zinc-900 bg-zinc-50/50 dark:bg-zinc-900/50">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-cyan-100 dark:bg-cyan-900/30 rounded-lg">
              <Bot className="w-5 h-5 text-cyan-600 dark:text-cyan-400" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">Configure Agent</h2>
              <p className="text-[11px] text-zinc-500 uppercase font-medium tracking-tight">Agent ID: NEW_AGENT_ID</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors">
            <X className="w-5 h-5 text-zinc-400" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 flex overflow-hidden">
          {/* Main Content (Left) */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            <div className="space-y-4">
              <h3 className="text-sm font-bold text-zinc-400 uppercase tracking-widest flex items-center gap-2">
                <Sparkles className="w-3.5 h-3.5" /> Identity & Role
              </h3>
              <div className="grid grid-cols-2 gap-4">
                <FieldGroup label="Role">
                  <TextInput value={data.role} onChange={(val) => setData({...data, role: val})} placeholder="e.g. Expert Analyst" />
                </FieldGroup>
              </div>
              <FieldGroup label="Goal" helperText="What is the objective of this agent?">
                <TextInput value={data.goal} onChange={(val) => setData({...data, goal: val})} multiline placeholder="Describe the goal..." />
              </FieldGroup>
              <FieldGroup label="Backstory">
                <TextInput value={data.backstory} onChange={(val) => setData({...data, backstory: val})} multiline placeholder="The origin story and expertise..." />
              </FieldGroup>

              <div className="grid grid-cols-2 gap-8 pt-4">
                <div className="space-y-4">
                   <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-tight flex items-center gap-2">
                    <Wrench className="w-3 h-3" /> Agent Tools
                   </h3>
                   <MultiSelector 
                      options={options?.tools || []}
                      selected={selectedTools}
                      onAdd={(val) => setSelectedTools([...(selectedTools || []), val])}
                      onRemove={(item) => setSelectedTools((selectedTools || []).filter(i => i !== item))}
                      placeholder="Select a tool..."
                   />
                </div>
                <div className="space-y-4">
                   <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-tight flex items-center gap-2">
                    <BookOpen className="w-3 h-3" /> Knowledge Sources
                   </h3>
                   <MultiSelector 
                      options={options?.knowledgeSources || []}
                      selected={selectedKnowledge}
                      onAdd={(val) => setSelectedKnowledge([...(selectedKnowledge || []), val])}
                      onRemove={(item) => setSelectedKnowledge((selectedKnowledge || []).filter(i => i !== item))}
                      placeholder="Select a source..."
                   />
                </div>
              </div>
            </div>
          </div>

          {/* Settings Sidebar (Right) */}
          <div className="w-[340px] border-l border-zinc-100 dark:border-zinc-900 overflow-y-auto bg-zinc-50/30 dark:bg-zinc-950/30">
            <Section title="Runtime Behavior" icon={Zap} defaultOpen={false}>
              <Toggle 
                label="Verbose Logging" 
                description="Show detailed execution logs"
                value={data.is_verbose} 
                onChange={(val) => setData({...data, is_verbose: val})} 
              />
              <Toggle 
                label="Allow Delegation" 
                description="Agent can ask others for help"
                value={data.allow_delegation} 
                onChange={(val) => setData({...data, allow_delegation: val})} 
              />
              <Toggle 
                label="Reasoning" 
                description="Show internal thought process"
                value={data.reasoning} 
                onChange={(val) => setData({...data, reasoning: val})} 
              />
              {data.reasoning === true && (
                <motion.div 
                  initial={{ opacity: 0, height: 0 }} 
                  animate={{ opacity: 1, height: 'auto' }}
                  className="pl-4 border-l-2 border-cyan-500/30 pt-2"
                >
                  <FieldGroup label="Max Reasoning Attempts" helperText="Max number of reasoning steps">
                    <NumberInput 
                      value={data.max_reasoning_attempts} 
                      onChange={(val) => setData({...data, max_reasoning_attempts: val})} 
                      placeholder="Default: None" 
                    />
                  </FieldGroup>
                </motion.div>
              )}
            </Section>

            <Section title="Cost Optimization" icon={DollarSign} defaultOpen={false}>
              <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <FieldGroup label="Max Iter" helperText="Default value is 25">
                  <NumberInput value={data.max_iter} onChange={(val) => setData({...data, max_iter: val})} placeholder="Default: 25" />
                </FieldGroup>
                <FieldGroup label="Max RPM" helperText="Max requests per minute">
                  <NumberInput value={data.max_rpm} onChange={(val) => setData({...data, max_rpm: val})} placeholder="∞" />
                </FieldGroup>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <FieldGroup label="Retry Limit" helperText="Default value is 2">
                  <NumberInput value={data.max_retry_limit} onChange={(val) => setData({...data, max_retry_limit: val})} placeholder="Default: 2" />
                </FieldGroup>
                <FieldGroup label="Execution Time" helperText="Limit in seconds">
                  <NumberInput value={data.max_execution_time} onChange={(val) => setData({...data, max_execution_time: val})} suffix="SEC" />
                </FieldGroup>
              </div>
              <Toggle 
                label="Context Window" 
                description="Respect context window"
                value={data.respect_context_window} 
                onChange={(val) => setData({...data, respect_context_window: val})} 
              />
              <Toggle 
                label="Cache" 
                description="Enable caching for this agent"
                value={data.cache} 
                onChange={(val) => setData({...data, cache: val})} 
              />
              </div>
            </Section>

            <Section title="Model Configuration" icon={Cpu} defaultOpen={false}>
              <div className="space-y-4">
                <SelectInput 
                  label="LLM Config" 
                  options={options?.llmModels || []}
                  value={data.llm_config_json} 
                  onChange={(val) => setData({...data, llm_config_json: val})} 
                />
                <SelectInput 
                    label="Func-Calling Config" 
                    options={options?.llmModels || []}
                    value={data.function_calling_llm_config_json} 
                    onChange={(val) => setData({...data, function_calling_llm_config_json: val})} 
                />
                <SelectInput 
                    label="Embedder" 
                    options={options?.embedders || []}
                    value={data.embedder_json} 
                    onChange={(val) => setData({...data, embedder_json: val})} 
                />
                <Toggle label="Multimodal" value={data.multimodal} onChange={(val) => setData({...data, multimodal: val})} />
                <Toggle label="Activate Skill" value={data.activate_skill} onChange={(val) => setData({...data, activate_skill: val})} />
              </div>
            </Section>

            <Section title="Date / Time Settings" icon={Clock} defaultOpen={false}>
               <div className="space-y-3">
                  <Toggle label="Inject Date" value={data.inject_date} onChange={(val) => setData({...data, inject_date: val})} />
                  <FieldGroup label="Date Format">
                    <TextInput value={data.date_format} onChange={(val) => setData({...data, date_format: val})} placeholder='Default is "%Y-%m-%d"' />
                  </FieldGroup>
               </div>
            </Section>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-zinc-100 dark:border-zinc-900 flex items-center justify-between bg-zinc-50/50 dark:bg-zinc-950">
          <p className="text-[11px] text-zinc-500 italic">Unset numeric values will use defaults.</p>
          <div className="flex items-center gap-3">
            <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors">
              Cancel
            </button>
            <button onClick={handleSave} className="px-6 py-2 text-sm font-semibold bg-cyan-600 text-white rounded-lg hover:bg-cyan-700 shadow-lg shadow-cyan-600/20 transition-all">
              Save Configuration
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
