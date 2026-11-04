#include "aquila/agent/orchestrator_module.hpp"
#include "aquila/modules/execution_module.hpp"
#include "aquila/modules/registry.hpp"
#include "aquila/modules/workspace_module.hpp"

namespace aquila {

ModuleRegistry ModuleRegistry::builtin() {
    ModuleRegistry r;
    r.register_module<WorkspaceModule>("WorkspaceModule");
    r.register_module<ExecutionModule>("ExecutionModule");
    r.register_module<OrchestratorModule>("OrchestratorModule");
    return r;
}

}  // namespace aquila
