// apps/aquila_gui/builder/cartridge_graph_bridge.hpp
#pragma once

#include "builder_data_models.hpp"
#include "aquila/types/recipe.hpp"

#include <QtNodes/DataFlowGraphModel>
#include <memory>

namespace aquila::gui {

class CartridgeGraphBridge {
public:
    static std::shared_ptr<QtNodes::NodeDelegateModelRegistry> createRegistry();

    static void loadCartridgeIntoModel(const RecipeCartridge& cartridge,
                                       QtNodes::DataFlowGraphModel& model);

    static RecipeCartridge extractCartridgeFromModel(QtNodes::DataFlowGraphModel& model);
};

}  // namespace aquila::gui
