import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "json.manager.project.source",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "ProjectSource") return;

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            origOnNodeCreated?.apply(this, arguments);

            // Update title when label changes
            const labelWidget = this.widgets?.find(w => w.name === "label");
            if (labelWidget) {
                const node = this;
                const origCallback = labelWidget.callback;
                labelWidget.callback = function (...args) {
                    origCallback?.apply(this, args);
                    node.title = labelWidget.value
                        ? `Source: ${labelWidget.value}`
                        : "Project Source";
                    app.graph?.setDirtyCanvas(true, true);
                };
                // Set initial title
                if (labelWidget.value) {
                    this.title = `Source: ${labelWidget.value}`;
                }
            }
        };

        const origOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (info) {
            origOnConfigure?.apply(this, arguments);
            const labelWidget = this.widgets?.find(w => w.name === "label");
            if (labelWidget?.value) {
                this.title = `Source: ${labelWidget.value}`;
            }
        };
    },
});
