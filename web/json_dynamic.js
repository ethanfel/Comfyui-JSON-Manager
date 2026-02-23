import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "json.manager.dynamic",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "JSONLoaderDynamic") return;

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            origOnNodeCreated?.apply(this, arguments);

            // Hide the output_keys widget (managed internally by JS)
            const okWidget = this.widgets?.find(w => w.name === "output_keys");
            if (okWidget) {
                okWidget.type = "hidden";
                okWidget.computeSize = () => [0, -4];
            }

            // Remove all 32 default outputs from Python RETURN_TYPES
            while (this.outputs.length > 0) {
                this.removeOutput(0);
            }

            // Add Refresh button
            this.addWidget("button", "Refresh Outputs", null, () => {
                this.refreshDynamicOutputs();
            });
        };

        nodeType.prototype.refreshDynamicOutputs = async function () {
            const pathWidget = this.widgets?.find(w => w.name === "json_path");
            const seqWidget = this.widgets?.find(w => w.name === "sequence_number");
            if (!pathWidget?.value) return;

            try {
                const resp = await api.fetchApi(
                    `/json_manager/get_keys?path=${encodeURIComponent(pathWidget.value)}&sequence_number=${seqWidget?.value || 1}`
                );
                const { keys } = await resp.json();

                // Update output_keys widget for Python to read at execution time
                const okWidget = this.widgets?.find(w => w.name === "output_keys");
                if (okWidget) okWidget.value = keys.join(",");

                // Remove all current outputs (disconnects links properly)
                while (this.outputs.length > 0) {
                    this.removeOutput(0);
                }

                // Add an output slot for each discovered key
                for (const key of keys) {
                    this.addOutput(key, "*");
                }

                this.setSize(this.computeSize());
                app.graph.setDirtyCanvas(true, true);
            } catch (e) {
                console.error("[JSONLoaderDynamic] Refresh failed:", e);
            }
        };

        // Restore state on workflow load
        const origOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (info) {
            origOnConfigure?.apply(this, arguments);

            const okWidget = this.widgets?.find(w => w.name === "output_keys");
            if (okWidget) {
                okWidget.type = "hidden";
                okWidget.computeSize = () => [0, -4];
            }

            const keys = okWidget?.value
                ? okWidget.value.split(",").filter(k => k.trim())
                : [];

            // On load, LiteGraph already restored serialized outputs with links.
            // Just rename to match keys (preserves links) and trim excess.
            for (let i = 0; i < this.outputs.length && i < keys.length; i++) {
                this.outputs[i].name = keys[i].trim();
            }

            // Remove any extra outputs beyond the key count
            while (this.outputs.length > keys.length) {
                this.removeOutput(this.outputs.length - 1);
            }

            this.setSize(this.computeSize());
        };
    },
});
