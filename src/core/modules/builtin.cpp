#include "aquila/agent/orchestrator_module.hpp"
#include "aquila/document/document_module.hpp"
#include "aquila/knowledge/knowledge_module.hpp"
#include "aquila/learn/learn_module.hpp"
#include "aquila/modules/execution_module.hpp"
#include "aquila/modules/registry.hpp"
#include "aquila/modules/workspace_module.hpp"
#include "aquila/persona/persona_module.hpp"

namespace aquila {

ModuleRegistry ModuleRegistry::builtin() {
    ModuleRegistry r;
    r.register_module<WorkspaceModule>("WorkspaceModule");
    r.register_module<ExecutionModule>("ExecutionModule");
    r.register_module<OrchestratorModule>("OrchestratorModule");
    r.register_module<knowledge::KnowledgeModule>("KnowledgeModule");
    r.register_module<document::DocumentModule>("DocumentModule");
    r.register_module<persona::PersonaModule>("PersonaModule");
    r.register_module<learn::LearnModule>("LearnModule");
    return r;
}

}  // namespace aquila
