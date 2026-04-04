import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "json.manager.binary_index_decoder",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "BinaryIndexDecoder") return;

        nodeType.prototype.onExecuted = function (output) {
            if (!output?.values) return;
            for (let i = 0; i < Math.min(output.values.length, this.outputs.length); i++) {
                const val = output.values[i];
                this.outputs[i].label = `${val}  ${this.outputs[i].name}`;
                this.outputs[i].color_on = (val === "true") ? "#4caf50" : "#888888";
                this.outputs[i].color_off = (val === "true") ? "#4caf50" : "#888888";
            }
            app.graph?.setDirtyCanvas(true, true);
        };
    },
});
