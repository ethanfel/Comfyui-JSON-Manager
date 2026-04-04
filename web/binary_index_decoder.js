import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "json.manager.binary_index_decoder",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "BinaryIndexDecoder") return;

        nodeType.prototype.onExecuted = function (output) {
            if (!output?.values) return;
            for (let i = 0; i < Math.min(output.values.length, this.outputs.length); i++) {
                this.outputs[i].label = `${output.values[i]}  ${this.outputs[i].name}`;
            }
            app.graph?.setDirtyCanvas(true, true);
        };
    },
});
