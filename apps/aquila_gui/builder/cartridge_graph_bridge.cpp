// apps/aquila_gui/builder/cartridge_graph_bridge.cpp
#include "cartridge_graph_bridge.hpp"

#include <QtNodes/Definitions>
#include <QPointF>

namespace aquila::gui {

std::shared_ptr<QtNodes::NodeDelegateModelRegistry> CartridgeGraphBridge::createRegistry() {
    auto reg = std::make_shared<QtNodes::NodeDelegateModelRegistry>();
    reg->registerModel<CartridgeRootNodeModel>(QStringLiteral("Core"));
    reg->registerModel<ModuleNodeModel>(QStringLiteral("Modules"));
    reg->registerModel<PreHookNodeModel>(QStringLiteral("Hooks"));
    reg->registerModel<ValidationHookNodeModel>(QStringLiteral("Gates"));
    reg->registerModel<ChecklistNodeModel>(QStringLiteral("Checklists"));
    reg->registerModel<IncludeNodeModel>(QStringLiteral("Includes"));
    return reg;
}

void CartridgeGraphBridge::loadCartridgeIntoModel(const RecipeCartridge& cartridge,
                                                   QtNodes::DataFlowGraphModel& model) {
    // 1. Clear existing nodes
    const auto existing = model.allNodeIds();
    for (const auto nid : existing) {
        model.deleteNode(nid);
    }

    // 2. Create Root Node
    const QtNodes::NodeId rootId = model.addNode(QStringLiteral("CartridgeRootNode"));
    model.setNodeData(rootId, QtNodes::NodeRole::Position, QPointF(550.0, 250.0));
    auto* root = model.delegateModel<CartridgeRootNodeModel>(rootId);
    if (root) {
        root->setRecipeId(QString::fromStdString(cartridge.recipe_id));
        root->setGoalTemplate(QString::fromStdString(cartridge.goal_template));
    }

    double currentY = 50.0;

    // 3. Includes
    if (!cartridge.include.empty()) {
        const QtNodes::NodeId incId = model.addNode(QStringLiteral("IncludeNode"));
        model.setNodeData(incId, QtNodes::NodeRole::Position, QPointF(50.0, currentY));
        auto* inc = model.delegateModel<IncludeNodeModel>(incId);
        if (inc) {
            inc->fromIncludes(cartridge.include);
        }
        model.addConnection(QtNodes::ConnectionId{incId, 0, rootId, 0});
        currentY += 120.0;
    }

    // 4. Modules
    for (std::size_t i = 0; i < cartridge.load_modules.size(); ++i) {
        const QtNodes::NodeId modId = model.addNode(QStringLiteral("ModuleNode"));
        model.setNodeData(modId, QtNodes::NodeRole::Position, QPointF(50.0, currentY));
        auto* mod = model.delegateModel<ModuleNodeModel>(modId);
        if (mod) {
            mod->fromModuleLoad(cartridge.load_modules[i]);
        }
        model.addConnection(QtNodes::ConnectionId{modId, 0, rootId, 1});
        currentY += 180.0;
    }

    // 5. Pre-LLM Hooks
    for (std::size_t i = 0; i < cartridge.pre_llm_hooks.size(); ++i) {
        const QtNodes::NodeId hkId = model.addNode(QStringLiteral("PreHookNode"));
        model.setNodeData(hkId, QtNodes::NodeRole::Position, QPointF(50.0, currentY));
        auto* hk = model.delegateModel<PreHookNodeModel>(hkId);
        if (hk) {
            hk->fromHookCall(cartridge.pre_llm_hooks[i]);
        }
        model.addConnection(QtNodes::ConnectionId{hkId, 0, rootId, 2});
        currentY += 140.0;
    }

    // 6. Scratchpad Checklist
    if (!cartridge.scratchpad_checklist.empty()) {
        const QtNodes::NodeId chId = model.addNode(QStringLiteral("ChecklistNode"));
        model.setNodeData(chId, QtNodes::NodeRole::Position, QPointF(50.0, currentY));
        auto* ch = model.delegateModel<ChecklistNodeModel>(chId);
        if (ch) {
            ch->fromChecklist(cartridge.scratchpad_checklist);
        }
        model.addConnection(QtNodes::ConnectionId{chId, 0, rootId, 3});
        currentY += 150.0;
    }

    // 7. Validation Exit Gate
    if (cartridge.post_llm_validation_hook.has_value()) {
        const QtNodes::NodeId vhId = model.addNode(QStringLiteral("ValidationHookNode"));
        model.setNodeData(vhId, QtNodes::NodeRole::Position, QPointF(50.0, currentY));
        auto* vh = model.delegateModel<ValidationHookNodeModel>(vhId);
        if (vh) {
            vh->fromValidationHook(*cartridge.post_llm_validation_hook);
        }
        model.addConnection(QtNodes::ConnectionId{vhId, 0, rootId, 4});
    }
}

RecipeCartridge CartridgeGraphBridge::extractCartridgeFromModel(QtNodes::DataFlowGraphModel& model) {
    RecipeCartridge out;

    CartridgeRootNodeModel* root = nullptr;
    const auto allNodes = model.allNodeIds();

    for (const auto nid : allNodes) {
        if (auto* r = model.delegateModel<CartridgeRootNodeModel>(nid)) {
            root = r;
            break;
        }
    }

    if (root) {
        out.recipe_id = root->recipeId().toStdString();
        out.goal_template = root->goalTemplate().toStdString();
    }

    for (const auto nid : allNodes) {
        if (auto* m = model.delegateModel<ModuleNodeModel>(nid)) {
            out.load_modules.push_back(m->toModuleLoad());
        } else if (auto* h = model.delegateModel<PreHookNodeModel>(nid)) {
            out.pre_llm_hooks.push_back(h->toHookCall());
        } else if (auto* v = model.delegateModel<ValidationHookNodeModel>(nid)) {
            out.post_llm_validation_hook = v->toValidationHook();
        } else if (auto* c = model.delegateModel<ChecklistNodeModel>(nid)) {
            out.scratchpad_checklist = c->toChecklist();
        } else if (auto* inc = model.delegateModel<IncludeNodeModel>(nid)) {
            out.include = inc->toIncludes();
        }
    }

    return out;
}

}  // namespace aquila::gui
