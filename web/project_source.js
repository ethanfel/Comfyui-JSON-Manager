import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "json.manager.project.source",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "ProjectSource") return;

        // Notify all ProjectKey nodes referencing this source to re-sync
        function notifyRelays(sourceNode) {
            if (!sourceNode.graph?._nodes) return;
            const labelW = sourceNode.widgets?.find(w => w.name === "label");
            if (!labelW?.value) return;
            console.log(`[ProjectSource] notifyRelays: label="${labelW.value}", scanning ${sourceNode.graph._nodes.length} nodes`);
            let matched = 0;
            for (const node of sourceNode.graph._nodes) {
                if (node.type === "ProjectKey" && node._syncFromSource && node._refreshKeys) {
                    const srcW = node.widgets?.find(w => w.name === "source_label");
                    console.log(`[ProjectSource]   ProjectKey id=${node.id} source_label="${srcW?.value}"`);
                    if (srcW?.value === labelW.value) {
                        matched++;
                        node._syncFromSource();
                        node._refreshKeys();
                    }
                }
            }
            console.log(`[ProjectSource] notifyRelays: matched ${matched} relays`);
        }

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            origOnNodeCreated?.apply(this, arguments);

            const node = this;

            // Hook all config widgets to notify relays on change
            for (const name of ["manager_url", "project_name", "file_name", "sequence_number"]) {
                const w = this.widgets?.find(w => w.name === name);
                if (w) {
                    const origCb = w.callback;
                    w.callback = function (...args) {
                        origCb?.apply(this, args);
                        notifyRelays(node);
                    };
                }
            }

            // Update title when label changes
            const labelWidget = this.widgets?.find(w => w.name === "label");
            if (labelWidget) {
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
